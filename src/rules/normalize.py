"""변형 표기 정규화 (이슈 #10).

이슈 #6, #8 탐색에서 모더레이션 분류기가 초성·글자 분리·모음 늘림 표기를 놓치고, 표준 표기로 바꾸면
점수가 올랐다. 이 모듈은 그 세 가지만 표준 표기로 바꾼다. 자모 분리(ㅅㅣ발), 특수문자·숫자 삽입(병.신, 시1발)은
분류기가 이미 처리하므로 건드리지 않는다. 영문 자판(tlqkf)과 공백 삽입은 표준 표기로 바꿔도 점수가
오르지 않아 범위에서 뺐다.

원문은 보존하고, 정규화본과 적용한 규칙 이름을 함께 돌려준다. 모델에는 원문과 정규화본을 둘 다 보내고
더 높은 점수를 쓰는 용도다.
"""

import re
from dataclasses import dataclass

# 한글 호환 자모(ㄱ-ㅎ, ㅏ-ㅣ). 초성만 단독으로 쓴 표기를 찾을 때 경계로 쓴다.
_JAMO = "ㄱ-ㅎㅏ-ㅣ"

# 초성 약어 → 표준 표기. 이번 탐색 문장에 나온 것과 흔한 욕설 초성만 둔다(공개 저장소라 최소한으로).
# 'ㅄ'는 'ㅂㅅ'과 다른 문자(자모 하나)라 따로 둔다.
INITIAL_SLANG = {
    "ㅅㅂ": "시발",
    "ㅆㅂ": "씨발",
    "ㅂㅅ": "병신",
    "ㅄ": "병신",
    "ㅈㄹ": "지랄",
    "ㅈㄹㄴ": "지랄",
    "ㄲㅈ": "꺼져",
    "ㄷㅊ": "닥쳐",
    "ㅁㅊ": "미친",
    "ㅈㄴ": "존나",
    "ㅅㄲ": "새끼",
}

_INITIALS_PATTERN = re.compile(
    rf"(?<![{_JAMO}])(?:{'|'.join(re.escape(key) for key in INITIAL_SLANG)})(?![{_JAMO}])"
)

# 글자 분리: 앞 음절만 완성하고 뒤 자음을 분리해 쓴 표기 (씨ㅂ럴 → 씨발)
_SPLIT_SSIBAL = re.compile(r"([시씨])ㅂ(?:[럴럼롬])?")

# 모음 늘림: 가운데에 '이'·'으'를 반복해 늘린 표기 (씨이이발 → 씨발)
_STRETCHED_SSIBAL = re.compile(r"([시씨])[이으]+발")


@dataclass(frozen=True)
class Normalization:
    original: str
    text: str
    applied: tuple

    @property
    def changed(self):
        return self.text != self.original


def normalize(text):
    """변형 표기를 표준 표기로 바꾼 결과를 돌려준다. 바꿀 것이 없으면 원문과 같다."""
    out = text
    applied = []

    def apply(name, pattern, repl):
        nonlocal out
        replaced = pattern.sub(repl, out)
        if replaced != out:
            applied.append(name)
            out = replaced

    apply("initial", _INITIALS_PATTERN, lambda match: INITIAL_SLANG[match.group(0)])
    apply("split", _SPLIT_SSIBAL, r"\1발")
    apply("stretched", _STRETCHED_SSIBAL, r"\1발")
    return Normalization(original=text, text=out, applied=tuple(applied))
