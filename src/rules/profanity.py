"""욕설 사전 (이슈 #10).

이슈 #6, #8 탐색에서 모더레이션 분류기는 욕설 단어가 단독·감탄으로 쓰이면 점수를 거의 주지 않았다
(`시발` 단독 0.055). 이 모듈은 **감탄으로도 쓸 수 없는 단어**만 사전으로 두고, 걸리면 알려 준다.

- 사전에 없는 말(미친, 존나, 개- 접두어 등 감탄으로 쓰는 말)은 아무 신호도 만들지 않는다. 허용 목록을 따로
  두지 않는다.
- 사전에 걸린 단어는 `HOLD`(사람 확인)의 근거가 된다. 사람을 향한 욕설은 모델이 이미 점수로 걸러 주고,
  최종 판정은 모델 점수와 합치는 단계에서 정한다.
- 한글은 띄어쓰기로 단어가 나뉘지 않아 글자 포함 여부만 보면 정상 단어(시발점, 병신년)가 걸린다. 팬 댓글에
  실제로 나올 법한 정상 단어만 예외로 두고(예외는 우회로가 될 수 있다), 나머지는 걸려도 HOLD라 비용이 작다.
  실제 데이터에서 오탐이 확인되면 그때 예외를 늘린다.
- 공개 저장소라 목록은 이번 탐색에 나온 최소한으로 둔다.

변형 표기(ㅅㅂ, 씨이이발 등)는 `normalize`로 표준 표기로 바꾼 문장을 넘겨 검사한다.
"""

import re
from dataclasses import dataclass

# (이름, 정규식). 이름은 결과 기록용이다.
PROFANITY_RULES = (
    # 시발점(始發點)은 "이 영상이 시작점이 됐다"처럼 팬 댓글에 쓰일 수 있어 제외한다.
    ("시발", re.compile(r"[시씨]발(?!점(?!심))")),
    ("지랄", re.compile(r"지랄")),
    # 병신년(丙申年)은 간지 표기라 제외한다.
    ("병신", re.compile(r"병신(?!년)")),
    # '새끼'는 동물 새끼(새끼 고양이, 새끼손가락)가 정상이라 욕설로 쓰인 형태만 잡는다.
    ("새끼", re.compile(r"(?:개|미친|병신|씨발|시발|지랄)\s*새끼|새끼(?:야|들아)")),
)


@dataclass(frozen=True)
class ProfanityHits:
    words: tuple

    @property
    def hit(self):
        return bool(self.words)


def analyze_profanity(text):
    """감탄으로도 쓸 수 없는 욕설 사전에 걸린 단어 이름을 돌려준다."""
    words = []
    for name, pattern in PROFANITY_RULES:
        if pattern.search(text) and name not in words:
            words.append(name)
    return ProfanityHits(words=tuple(words))
