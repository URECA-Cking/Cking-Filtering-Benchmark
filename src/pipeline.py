"""필터링 파이프라인 (이슈 #10).

한 댓글을 정규화하고, 모델에 원문과 정규화본을 모두 보내 위반으로 판정되는 쪽을 쓰고, 규칙 신호와 합쳐
최종 PASS / BLOCK을 정한다. 모델 호출은 함수로 주입받아 API 없이도 시험할 수 있다.

모델 점수, 규칙 신호, 최종 판정을 따로 남겨 어느 단계가 막았는지 알 수 있게 한다. 모델 호출이 실패하면
판별 성능과 섞지 않도록 상태(modelStatus)를 따로 기록하고, 그때는 규칙 신호만으로 판정한다.
"""

from dataclasses import dataclass

from src.rules.decision import Decision, decide
from src.rules.normalize import Normalization, normalize
from src.rules.patterns import PatternHits, analyze_patterns
from src.rules.profanity import ProfanityHits, analyze_profanity


@dataclass(frozen=True)
class PipelineResult:
    normalization: Normalization
    model_original: dict
    model_normalized: dict  # 정규화로 문장이 바뀌지 않았으면 None
    model_status: str  # ok | error | timeout | not_run
    model_flagged: bool
    patterns: PatternHits
    profanity: ProfanityHits
    decision: Decision


def _model_status(results):
    for result in results:
        if result.get("apiStatus") != "ok":
            return result.get("apiStatus", "error")
    return "ok"


def _blocks_for_model_result(result):
    """Ignore a moderation flag only when every flagged category is self-harm.

    Self-harm is outside this benchmark's ABUSE/HATE/SPAM/PRIVACY policy.
    Keep an unclassified flag blocking so incomplete API responses do not
    silently pass.
    """
    if not result.get("flagged"):
        return False
    categories = result.get("flaggedCategories")
    if categories and all(category.startswith("self-harm") for category in categories):
        return False
    return True


def evaluate(text, model_call):
    """model_call(text)는 {"apiStatus": "ok", "flagged": bool, ...} 형태를 돌려주는 함수다."""
    normalization = normalize(text)
    model_original = model_call(text)
    model_normalized = model_call(normalization.text) if normalization.changed else None

    results = [r for r in (model_original, model_normalized) if r is not None]
    ok_results = [r for r in results if r.get("apiStatus") == "ok"]
    model_flagged = any(_blocks_for_model_result(r) for r in ok_results)

    patterns = analyze_patterns(text)
    profanity = analyze_profanity(normalization.text)
    return PipelineResult(
        normalization=normalization,
        model_original=model_original,
        model_normalized=model_normalized,
        model_status=_model_status(results),
        model_flagged=model_flagged,
        patterns=patterns,
        profanity=profanity,
        decision=decide(model_flagged, patterns, profanity),
    )


def to_record(result):
    """결과를 JSONL로 남길 dict로 바꾼다. 모델 점수, 규칙 신호, 최종 판정을 따로 담는다."""
    return {
        "modelStatus": result.model_status,
        "model": {
            "original": result.model_original,
            "normalized": result.model_normalized,
            "flagged": result.model_flagged,
        },
        "rules": {
            "normalizedText": result.normalization.text if result.normalization.changed else None,
            "normalizationApplied": list(result.normalization.applied),
            "spam": list(result.patterns.spam),
            "privacy": list(result.patterns.privacy),
            "profanity": list(result.profanity.words),
        },
        "final": {"action": result.decision.action, "reasons": list(result.decision.reasons)},
    }
