"""필터링 파이프라인 실제 호출 검증 (이슈 #10).

탐색용 문장을 파이프라인(정규화 + 모델 + 규칙)으로 돌려, 모델만 쓸 때와 최종 판정이 어떻게 달라지는지 비교한다.
정답 라벨은 모두 사람 검수 전이라 정확도 지표가 아니라 탐색이다. 정답이 HOLD인 문장은 점수에 넣지 않고 참고로만 보여 준다.

사용법 (저장소 루트에서)
    export OPENAI_API_KEY=...        # 키는 환경변수로만 전달한다
    python -m src.check_pipeline --data data/probes.jsonl
    python -m src.check_pipeline --data data/probes_normalized.jsonl --details
    python -m src.check_pipeline --dry-run   # 모델 호출 없이 규칙만 확인
    python -m src.check_pipeline --data data/context_eval.jsonl --split dev   # 문맥 평가 세트의 개발용만

문맥 평가 세트(data/context_eval.jsonl)는 개발용(dev)과 최종 평가용(final)이 나뉘어 있다. 최종 평가용은 방법을 확정한 뒤
한 번만 보는 데이터라서, 기본은 개발용만 돌리고 최종 평가용은 --allow-final을 줘야 돌아간다. split이 없는 이전 탐색 데이터는
개발용으로 본다.

데이터 경로를 여러 번 지정할 수 있다. 결과는 results/ 아래 JSONL로 저장한다(Git에 포함하지 않는다).
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from src import smoke_check
from src.pipeline import evaluate, to_record

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = ["data/samples.jsonl", "data/probes.jsonl", "data/probes_normalized.jsonl", "data/probes_profanity.jsonl"]


def build_model_call(api_key, timeout, dry_run):
    def call(text):
        if dry_run:
            return {"apiStatus": "not_run"}
        result = smoke_check.call_openai(text, api_key, timeout, smoke_check.OPENAI_MODEL)
        time.sleep(0.2)  # 호출 사이 간격
        return result

    return call


def model_only_blocks(record):
    """모델만 썼을 때(원문만 보냈을 때)의 판정."""
    original = record["model"]["original"]
    return original.get("apiStatus") == "ok" and bool(original.get("flagged"))


def summarize(entries, details, dry_run=False):
    groups = {"BLOCK": [], "PASS": [], "HOLD": []}
    for entry in entries:
        groups[entry["expectedAction"]].append(entry)

    def count(items, key):
        return sum(1 for item in items if key(item))

    block, pass_, hold = groups["BLOCK"], groups["PASS"], groups["HOLD"]
    if dry_run:
        print("\n=== 규칙만 실행한 결과 (모델 미호출) ===")
        for action, items in (("BLOCK", block), ("PASS", pass_), ("HOLD", hold)):
            print(f"정답 {action} {len(items)}건: BLOCK 판정 {count(items, lambda e: e['final'] == 'BLOCK')}건")
    else:
        print("\n=== 정답별 비교 (모델만 → 파이프라인) ===")
        print(f"정답 BLOCK {len(block)}건: BLOCK 판정 {count(block, lambda e: e['modelOnly'])}건 → "
              f"{count(block, lambda e: e['final'] == 'BLOCK')}건")
        print(f"정답 PASS  {len(pass_)}건: 오탐(BLOCK) {count(pass_, lambda e: e['modelOnly'])}건 → "
              f"{count(pass_, lambda e: e['final'] == 'BLOCK')}건")
        print(f"정답 HOLD  {len(hold)}건 (참고): BLOCK 판정 {count(hold, lambda e: e['modelOnly'])}건 → "
              f"{count(hold, lambda e: e['final'] == 'BLOCK')}건")
    if not dry_run:
        failed = count(entries, lambda e: e["modelStatus"] != "ok" and e["modelStatus"] != "not_run")
        print(f"모델 호출 실패·시간 초과: {failed}건 (판별 지표에서 따로 본다)")

    platforms = sorted({e.get("platform") for e in entries if e.get("platform")})
    if platforms:
        print("\n=== 플랫폼별 오탐·미탐 ===")
        for platform in platforms:
            platform_entries = [e for e in entries if e.get("platform") == platform]
            normal = [e for e in platform_entries if e["expectedAction"] == "PASS"]
            violations = [e for e in platform_entries if e["expectedAction"] == "BLOCK"]
            false_positives = count(normal, lambda e: e["final"] == "BLOCK")
            false_negatives = count(violations, lambda e: e["final"] != "BLOCK")
            print(f"  {platform}: 오탐 {false_positives}/{len(normal)}, 미탐 {false_negatives}/{len(violations)}")

    if not dry_run:
        changed = [e for e in entries if e["modelOnly"] != (e["final"] == "BLOCK")]
        print(f"\n=== 모델만 쓸 때와 판정이 달라진 문장 {len(changed)}건 ===")
        for e in changed:
            move = "PASS → BLOCK" if e["final"] == "BLOCK" else "BLOCK → PASS"
            print(f"  {e['id']} [{move}] 정답={e['expectedAction']} 근거={','.join(e['reasons'])} | {e['text']}")

    wrong = [e for e in entries
             if (e["expectedAction"] == "BLOCK" and e["final"] != "BLOCK")
             or (e["expectedAction"] == "PASS" and e["final"] == "BLOCK")]
    print(f"\n=== 파이프라인 후에도 정답과 다른 문장 {len(wrong)}건 (HOLD 정답 제외) ===")
    for e in wrong:
        kind = "놓침" if e["expectedAction"] == "BLOCK" else "오탐"
        print(f"  {e['id']} [{kind}] 최종={e['final']} 근거={','.join(e['reasons']) or '-'} | {e['text']}")

    if details:
        print("\n=== 전체 ===")
        for e in entries:
            print(f"  {e['id']}: 정답={e['expectedAction']} 모델만={'BLOCK' if e['modelOnly'] else 'PASS'} "
                  f"최종={e['final']} 근거={','.join(e['reasons']) or '-'}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", action="append", help="평가 데이터 JSONL (여러 번 지정 가능, 기본: 탐색 데이터 전체)")
    parser.add_argument("--limit", type=int, default=0, help="파일마다 앞에서 N건만")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--split", choices=["dev", "final", "all"], default="dev",
                        help="평가 데이터 구분 (기본: dev). final·all은 --allow-final이 필요하다")
    parser.add_argument("--allow-final", action="store_true",
                        help="최종 평가용 데이터를 돌리는 것을 허용한다. 방법을 확정한 뒤 한 번만 쓴다")
    parser.add_argument("--dry-run", action="store_true", help="모델 호출 없이 규칙만 확인")
    parser.add_argument("--details", action="store_true", help="모든 문장의 판정을 출력")
    args = parser.parse_args()

    if args.split in ("final", "all") and not args.allow_final:
        sys.exit("최종 평가용(final) 데이터는 방법을 확정한 뒤 한 번만 봅니다. 정말 돌리려면 --allow-final을 주세요.")

    api_key = os.environ.get("OPENAI_API_KEY")
    if not args.dry_run and not api_key:
        sys.exit("OPENAI_API_KEY 환경변수가 없습니다. 키는 환경변수로만 전달하세요.")

    rows = []
    for path in args.data or DEFAULT_DATA:
        rows += smoke_check.load_samples(args.limit, ROOT / path)

    rows = [row for row in rows if args.split == "all" or row.get("split", "dev") == args.split]

    model_call = build_model_call(api_key, args.timeout, args.dry_run)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    entries, records = [], []
    for row in rows:
        result = evaluate(row["text"], model_call)
        record = {"runId": run_id, "commentId": row["id"], "expectedAction": row["expectedAction"],
                  "expectedCategories": row["categories"], **to_record(result)}
        records.append(record)
        entries.append({
            "id": row["id"], "text": row["text"], "expectedAction": row["expectedAction"],
            "platform": row.get("platform"),
            "final": result.decision.action, "reasons": result.decision.reasons,
            "modelOnly": model_only_blocks(record), "modelStatus": result.model_status,
        })

    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"pipeline-{run_id}.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"문장 {len(entries)}건 처리")
    summarize(entries, args.details, args.dry_run)
    print(f"\n저장: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
