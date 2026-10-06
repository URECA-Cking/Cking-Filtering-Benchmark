"""로컬 전용 필터링 파이프라인 (이슈 #17).

한 댓글을 정규화하고, 규칙(스팸·개인정보·욕설 사전)과 로컬 2차 모델 점수를 합쳐 최종 PASS / BLOCK을
정한다. 외부 API를 부르지 않는다. 판정 규칙은 `src/rules/decision.py`를 그대로 쓰고, 모델이 막은 경우의
근거 이름만 `classifier`로 남긴다.

평가에서 검증한 동작과 같게 맞췄다.
- 모델에는 원문만 넣는다(정규화본은 점수 내지 않는다).
- 점수가 임계값 이상이면(`>=`) 막는다. 기본 임계값은 0.95다.
- 스팸·개인정보 규칙은 원문(NFKC 맞춤)에, 욕설 사전은 정규화본에 건다.
- 모델은 최대 길이(모델 설정 `maxLength`, 현재 192 토큰)까지만 읽는다. 더 긴 댓글의 뒷부분은 점수에
  반영되지 않지만 규칙은 전체 문장에 건다.

모델 점수 계산은 함수로 주입받아 모델 없이도 시험할 수 있다. 점수를 못 구하면 예외를 그대로 올린다.
조용히 통과시키지 않으므로 호출하는 쪽이 처리 방식을 정한다.

사용법 (저장소 루트에서)
    python -m src.local_pipeline --text "검사할 댓글"
    python -m src.local_pipeline --data data/probes.jsonl --output results/local-probes.jsonl
"""

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from src.rules.decision import Decision, decide
from src.rules.normalize import Normalization, normalize
from src.rules.patterns import PatternHits, analyze_patterns
from src.rules.profanity import ProfanityHits, analyze_profanity

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "results/kold-classifier/threat-ctx-v1-reviewed/best"
THRESHOLD = 0.95
MODEL_REASON = "classifier"


@dataclass(frozen=True)
class LocalResult:
    normalization: Normalization
    score: float
    threshold: float
    model_flagged: bool
    patterns: PatternHits
    profanity: ProfanityHits
    decision: Decision


def evaluate_local(text, score_fn, threshold=THRESHOLD):
    """score_fn(text)는 위반(1) 확률을 0~1 사이 실수로 돌려주는 함수다."""
    normalization = normalize(text)
    score = float(score_fn(text))
    model_flagged = score >= threshold
    patterns = analyze_patterns(text)
    profanity = analyze_profanity(normalization.text)
    return LocalResult(
        normalization=normalization,
        score=score,
        threshold=threshold,
        model_flagged=model_flagged,
        patterns=patterns,
        profanity=profanity,
        decision=decide(model_flagged, patterns, profanity, model_reason=MODEL_REASON),
    )


def to_record(result):
    """결과를 dict로 바꾼다. 모델 점수, 규칙 신호, 최종 판정을 따로 담아 어느 단계가 막았는지 알 수 있다."""
    return {
        "final": {"action": result.decision.action, "reasons": list(result.decision.reasons)},
        "model": {"score": round(result.score, 6), "threshold": result.threshold,
                  "flagged": result.model_flagged},
        "rules": {
            "normalizedText": result.normalization.text if result.normalization.changed else None,
            "normalizationApplied": list(result.normalization.applied),
            "spam": list(result.patterns.spam),
            "privacy": list(result.patterns.privacy),
            "profanity": list(result.profanity.words),
        },
    }


class LocalClassifier:
    """저장된 댓글 분류 모델을 읽어 위반 확률을 계산한다. torch는 만들 때 불러온다."""

    def __init__(self, model_dir=MODEL_DIR, threads=None):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        model_dir = Path(model_dir)
        config_path = model_dir / "stage2_config.json"
        if not config_path.is_file():
            raise FileNotFoundError(f"모델 설정 파일이 없습니다: {config_path}")
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if config.get("mode") != "comment":
            raise ValueError(f"댓글 단독 입력 모델이 아닙니다: {model_dir}")
        if threads:
            torch.set_num_threads(threads)
        self._torch = torch
        self.max_length = config["maxLength"]
        self._tokenizer = AutoTokenizer.from_pretrained(model_dir)
        self._model = AutoModelForSequenceClassification.from_pretrained(model_dir)
        self._model.eval()

    def __call__(self, text):
        encoded = self._tokenizer(text, truncation=True, max_length=self.max_length,
                                  return_tensors="pt")
        with self._torch.inference_mode():
            logits = self._model(**encoded).logits
        return self._torch.softmax(logits, dim=-1)[0, 1].item()


class LocalFilter:
    """서비스에서 쓰는 진입점이다. 모델은 한 번만 읽고 `moderate`를 반복 호출한다."""

    def __init__(self, model_dir=MODEL_DIR, threshold=THRESHOLD, threads=None, score_fn=None):
        if not 0 <= threshold <= 1:
            raise ValueError("임계값은 0~1 사이여야 합니다")
        self.threshold = threshold
        self.score_fn = score_fn or LocalClassifier(model_dir, threads)

    def moderate(self, text):
        return to_record(evaluate_local(text, self.score_fn, self.threshold))


def _read_rows(path):
    with path.open(encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream if line.strip()]
    if not rows or any("text" not in row for row in rows):
        raise ValueError(f"'text' 필드가 있는 JSONL이 아닙니다: {path}")
    return rows


def _summarize(entries):
    """정답(expectedAction)이 PASS/BLOCK인 문장만 센다. HOLD(경계)는 점수에 넣지 않는다."""
    block = [e for e in entries if e["expectedAction"] == "BLOCK"]
    passed = [e for e in entries if e["expectedAction"] == "PASS"]
    if not block and not passed:
        return
    caught = sum(e["action"] == "BLOCK" for e in block)
    false_blocks = [e for e in passed if e["action"] == "BLOCK"]
    skipped = len(entries) - len(block) - len(passed)
    print(f"차단 {caught}/{len(block)} | 정상 오차단 {len(false_blocks)}/{len(passed)}"
          + (f" | 점수 제외(HOLD 등) {skipped}건" if skipped else ""))
    missed = Counter(e.get("caseType") or "-" for e in block if e["action"] != "BLOCK")
    if missed:
        print("놓친 유형:", dict(missed))
    for e in false_blocks:
        print(f"  오차단 {e['id']} 근거={','.join(e['reasons'])} | {e['text']}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", help="검사할 댓글 한 건")
    source.add_argument("--data", type=Path, help="검사할 JSONL (각 줄에 text 필드)")
    parser.add_argument("--output", type=Path, help="--data 결과 JSONL 경로. 이미 있으면 중단")
    parser.add_argument("--model-dir", type=Path, default=MODEL_DIR)
    parser.add_argument("--threshold", type=float, default=THRESHOLD)
    parser.add_argument("--threads", type=int, default=None)
    args = parser.parse_args()
    if not 0 <= args.threshold <= 1:
        parser.error("--threshold는 0~1 사이여야 합니다")
    if args.output and args.data is None:
        parser.error("--output은 --data와 함께 씁니다")
    if args.output and args.output.exists():
        parser.error(f"결과 파일이 이미 있습니다. 덮어쓰지 않습니다: {args.output}")
    rows = _read_rows(args.data) if args.data else [{"id": "text", "text": args.text}]

    moderator = LocalFilter(args.model_dir, args.threshold, args.threads)
    entries, records = [], []
    for index, row in enumerate(rows, 1):
        comment_id = row.get("id", f"row-{index}")
        record = moderator.moderate(row["text"])
        records.append({"commentId": comment_id, "expectedAction": row.get("expectedAction"), **record})
        entries.append({"id": comment_id, "text": row["text"], "caseType": row.get("caseType"),
                        "expectedAction": row.get("expectedAction"),
                        "action": record["final"]["action"], "reasons": record["final"]["reasons"]})

    if args.text:
        print(json.dumps(records[0], ensure_ascii=False, indent=2))
        return
    print(f"문장 {len(entries)}건 처리 | BLOCK {sum(e['action'] == 'BLOCK' for e in entries)}건")
    _summarize(entries)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8", newline="\n") as stream:
            for record in records:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"저장: {args.output}")


if __name__ == "__main__":
    main()
