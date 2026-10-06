"""최종 판정 결합 (이슈 #10).

모델 판정과 규칙 신호(스팸·개인정보, 욕설 사전)를 합쳐 최종 PASS / BLOCK을 정한다. 사람이 확인하지 않는
구조라 결과는 두 값뿐이고, 애매한 경우의 처리는 아래 규칙으로 고정한다.

BLOCK이 되는 경우 (하나라도 해당하면)
- 모델이 위반으로 판정함
- 욕설 사전에 걸림 (감탄으로 쓰여도 허용하지 않는다고 정했다)
- 개인정보 규칙에 걸림
- 스팸 규칙에 걸림. 링크가 있는 댓글도 스팸 규칙(`link`)이므로 막는다(링크는 모두 거른다고 정했다).

각 BLOCK에는 근거(reasons)를 남겨 거절 안내와 점검에 쓸 수 있게 한다.
"""

from dataclasses import dataclass

PASS = "PASS"
BLOCK = "BLOCK"


@dataclass(frozen=True)
class Decision:
    action: str
    reasons: tuple


def decide(model_flagged, patterns, profanity, model_reason="model"):
    """model_reason은 모델이 막았을 때 남기는 근거 이름이다. 저장된 API 결과와 구분하려고 바꿀 수 있다."""
    reasons = []
    if model_flagged:
        reasons.append(model_reason)
    reasons += [f"profanity:{word}" for word in profanity.words]
    reasons += [f"privacy:{name}" for name in patterns.privacy]
    reasons += [f"spam:{name}" for name in patterns.spam]
    return Decision(action=BLOCK if reasons else PASS, reasons=tuple(reasons))
