"""스팸·개인정보 규칙 (이슈 #10).

이슈 #6 탐색에서 모더레이션 분류기는 스팸·광고와 개인정보를 분류 항목으로 갖고 있지 않아 모두 놓쳤다.
이 모듈은 그 두 유형을 정규식으로 잡는다. 판정(PASS/HOLD/BLOCK)은 여기서 하지 않고, 어떤 규칙에 걸렸는지만
돌려준다. 최종 판정은 모델 점수와 욕설 사전 신호를 합치는 단계에서 한다.

규칙은 오탐을 줄이는 쪽으로 보수적으로 만들었고, 이슈 #6·#8 탐색 문장과 정상 문장으로 검증한다.
"""

import re
import unicodedata
from dataclasses import dataclass

# ---- 개인정보 ----

_PHONE_MOBILE = re.compile(r"(?<!\d)01[016789][\s.\-]?\d{3,4}[\s.\-]?\d{4}(?!\d)")
# 지역번호 유선전화는 구분 기호가 있을 때만 잡는다(숫자만 이어진 일반 숫자와 구분하려고).
_PHONE_LANDLINE = re.compile(r"(?<!\d)0(?:2|[3-6][1-5])[\s.\-]\d{3,4}[\s.\-]\d{4}(?!\d)")
# '공일공 일이삼사 …'처럼 숫자를 한글로 풀어 쓴 휴대전화 번호
_PHONE_HANGUL = re.compile(r"(?:공|영)\s*일\s*(?:공|영)(?:[\s\-.]*[공영일이삼사오육칠팔구]){7,8}")
_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# 주민등록번호 형식. 생년월일이 달력상 가능한 값일 때만 잡는다.
_RRN = re.compile(r"(?<!\d)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])[\s\-]?[1-4]\d{6}(?!\d)")
# '카카오톡 아이디는 abc123' 같은 메신저·SNS 계정 안내
_ACCOUNT = re.compile(
    r"(?:카톡|카카오톡|카카오|인스타그램|인스타|텔레그램|디스코드|라인)[^\n]{0,12}?(?:아이디|계정|id)"
    r"[^A-Za-z0-9\n]{0,8}[A-Za-z0-9._]{4,}",
    re.IGNORECASE,
)
# '서울시 ○○구 ○○로 12'처럼 도로명 주소 형식(번지까지 있을 때만)
_ADDRESS = re.compile(r"[가-힣]+(?:시|도)\s*[가-힣]+(?:구|군|시)\s*[가-힣0-9]+(?:로|길)\s*\d+")

PRIVACY_RULES = (
    ("phone", _PHONE_MOBILE),
    ("phone", _PHONE_LANDLINE),
    ("phone", _PHONE_HANGUL),
    ("email", _EMAIL),
    ("rrn", _RRN),
    ("account", _ACCOUNT),
    ("address", _ADDRESS),
)

# ---- 스팸·광고 ----

# 스킴이 있는 주소, 또는 흔한 최상위 도메인이 붙은 주소(t.me/..., naver.com 등)
_LINK = re.compile(
    r"(?:https?://|www\.)\S+"
    r"|\b(?:[a-z0-9-]+\.)+(?:com|net|org|co\.kr|kr|io|me|ly|gl|app|xyz|shop|link|invalid)\b(?:/\S*)?",
    re.IGNORECASE,
)
# 금전·가입 유도에 쓰이는 확실한 문구만 둔다('선착순'처럼 정상 대화에도 나오는 말은 뺐다).
_SOLICIT = re.compile(r"수익\s*보장|무료\s*코인|재택\s*알바|부업\s*(?:문의|추천)|대출\s*상담|투자\s*(?:문의|상담)|오픈\s*채팅")
# 맞구독·맞팔 요청
_ENGAGEMENT_BAIT = re.compile(r"맞구독|맞팔|구독\s*(?:좋아요\s*)?(?:알림\s*)?부탁")

SPAM_RULES = (
    ("link", _LINK),
    ("solicit", _SOLICIT),
    ("engagement_bait", _ENGAGEMENT_BAIT),
)

# 도배: 같은 낱말·구절이 이 횟수 이상 반복되면 걸린다. 웃음·울음 표기(ㅋㅋ, ㅠㅠ)는 제외한다.
_FLOOD_REPEATS = 4
_FLOOD_MIN_LENGTH = 4
_FILLER_TOKEN = re.compile(r"^[ㅋㅎㅠㅜ.!?~]+$")


@dataclass(frozen=True)
class PatternHits:
    spam: tuple
    privacy: tuple

    @property
    def spam_hit(self):
        return bool(self.spam)

    @property
    def privacy_hit(self):
        return bool(self.privacy)


def _match(rules, text):
    names = []
    for name, pattern in rules:
        if pattern.search(text) and name not in names:
            names.append(name)
    return names


def _is_flood(text):
    tokens = [token for token in text.split() if not _FILLER_TOKEN.match(token)]
    for size in (1, 2, 3):
        counts = {}
        for index in range(len(tokens) - size + 1):
            phrase = " ".join(tokens[index:index + size])
            if len(phrase.replace(" ", "")) >= _FLOOD_MIN_LENGTH:
                counts[phrase] = counts.get(phrase, 0) + 1
        if any(count >= _FLOOD_REPEATS for count in counts.values()):
            return True
    return False


def analyze_patterns(text):
    """스팸·개인정보 규칙에 걸린 규칙 이름을 돌려준다. 전각 숫자 등은 NFKC로 맞춘 뒤 검사한다."""
    normalized = unicodedata.normalize("NFKC", text)
    spam = _match(SPAM_RULES, normalized)
    if _is_flood(normalized):
        spam.append("flood")
    return PatternHits(spam=tuple(spam), privacy=tuple(_match(PRIVACY_RULES, normalized)))
