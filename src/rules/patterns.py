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
_SOLICIT = re.compile(r"수익\s*보장|무료\s*코인|재택\s*알바|부업\s*(?:문의|추천)|대출\s*상담|투자\s*(?:문의|상담)|오픈\s*채팅|(?:재택|부업)\s*(?:하실|구해|구합|모집)")
# 맞구독·맞팔 요청
# '맞팔 요청이 너무 많이 와요' 같은 푸념은 걸리지 않도록 요청·제안 형태만 잡는다.
_ENGAGEMENT_BAIT = re.compile(
    r"(?:맞구독|맞팔|선팔)(?:\s*(?:맞구독|맞팔|선팔))?\s*(?:해|하실|하자|하면|하러|해드|환영|부탁|합시다|가요|가자|구해|원해|할\s*분|바랍|받습니다|받아요)"
    r"|구독\s*(?:좋아요\s*)?(?:알림\s*)?부탁"
)

# 팔로워·좋아요·조회수를 늘려 주거나 판다는 문구. '팔로워 늘리는 법' 같은 질문은 걸리지 않는다.
_FOLLOWER_SALE = re.compile(
    r"(?:팔로워|구독자|좋아요|조회수|시청자)[^\n]{0,12}?"
    r"(?:늘려\s*드|올려\s*드|판매|팝니다|팔아요|대량\s*(?:증가|구매|주문)|증가\s*(?:서비스|작업)"
    r"|작업\s*(?:해|합니다)|\d+\s*(?:천|만)?\s*원)"
)
# 판매자 말투. '현장 판매 굿즈', '공구 오픈하면 알려주세요' 같은 팬 댓글은 걸리지 않는다.
_SALE = re.compile(
    r"팝니다|팔아요|(?:판매|공구)\s*(?:합니다|해요|해드려요|중입니다|중이에요|중\s*문의)"
    r"|공구\s*오픈\s*(?:했|합)"
)

SPAM_RULES = (
    ("link", _LINK),
    ("solicit", _SOLICIT),
    ("engagement_bait", _ENGAGEMENT_BAIT),
    ("follower_sale", _FOLLOWER_SALE),
    ("sale", _SALE),
)

# 공백·점·기호를 끼워 넣은 우회 표기('수 익 인증', '텔.레.그.램')도 잡도록 구분 기호를 뺀 문장에 거는 규칙이다.
# 확실한 투자·도박 유도 문구만 둔다. 숫자가 섞인 문구는 단어 경계가 흐려지므로 금액 주장에 한정한다.
_COMPACT = re.compile(r"[\s.·,\-_/|*~`'\"]+")
# 투자·도박 주제어는 경고·피해 후기 댓글에도 흔하다('리딩방 사기 조심하세요', '먹튀 피해 예방 영상 감사합니다').
# 그래서 주제어만으로는 걸지 않고, 같은 문장에 가입·문의 같은 유도 표현이 함께 있을 때만 잡는다.
# 금액·수익을 직접 내세우는 문구(_INVEST_CLAIM)는 유도 표현 없이도 홍보 주장이므로 단독으로 잡는다.
_INVEST_CLAIM = re.compile(
    r"수익률?\d+%(?:인증|보장|확정|달성)|수익인증(?:해드|합니다|드려|많|확실|가능)"
    r"|(?:한달에?|월)(?:\d+|천|백)만?원?(?:버는|벌고|벌수)"
    r"|일당\d+만?원?(?:가능|보장|확실|지급|즉시)"
)
_INVEST_TOPIC = re.compile(
    r"리딩방|시그널(?:방|공유)|(?:주식|코인|선물)(?:리딩|시그널)"
    r"|원금보장(?![은이도]?(?:안|불가|없|아니|되지))|고수익|확정수익|신용불량|당일대출"
)
_GAMBLING_TOPIC = re.compile(
    r"바카라|먹튀|슬롯사이트|온라인(?:카지노|도박)|카지노(?:\S{0,6})사이트|카지노(?:가입|보너스|이벤트)"
    r"|(?:스포츠)?토토(?:사이트|분석|추천|가입)|(?:첫충|신규가입)보너스"
    r"|적중률\d+%|승부예측|픽공유|프로토분석|배팅방|베팅방"
)
# 주제어와 같은 문장에서 가입·문의·제공을 권하는 표현. 경고문에 흔한 '조심하세요', '믿지 마세요'는 넣지 않았다.
_TOPIC_LURE = re.compile(
    r"입장(?:하세요|해|링크|문의|방법|코드|안내)|가입(?:하세요|해|링크|문의|코드|방법|시|환영)"
    r"|문의|상담|신청|예약|링크|프로필|dm|디엠|쪽지|카톡|텔레|오픈채팅|운영(?:중|합니다|해요)|모집"
    r"|드립니다|드려요|드릴게요|알려드|추천(?:드려요|드립니다|합니다|해요)|무료|보너스|이벤트|혜택|지급"
    r"|지원하세요|안내|(?<!불)가능(?:합니다|해요|하세요)",
    re.IGNORECASE,
)
COMPACT_CLAIM_RULES = (("invest", _INVEST_CLAIM),)
COMPACT_TOPIC_RULES = (
    ("invest", _INVEST_TOPIC),
    ("gambling", _GAMBLING_TOPIC),
)

# 외부 이동·문의를 권하는 말투와 혜택·판매 단어가 함께 있을 때만 홍보로 본다. 각각은 정상 댓글에도 흔하다
# ('굿즈 할인 언제 해요', '협업 문의는 DM으로 주세요', '링크 확인해 보겠습니다').
_LURE = re.compile(
    r"(?:프로필|링크|DM|디엠|쪽지|오픈\s*(?:채팅|카톡)|텔레(?:그램)?|카톡)[^.!?\n]{0,15}"
    r"(?:주세요|주시면|하세요|환영|오세요|확인하세요|클릭|이용하세요|바랍니다)"
    r"|(?:문의|상담|연락|신청|예약)\s*(?:주세요|환영|바랍니다)"
    r"|(?:문의|상담|신청|예약)(?:는|은)\s*(?:프로필|링크|DM|디엠|쪽지|카톡|텔레)"
    r"|(?:문의|상담|신청|예약)\s*(?:DM|디엠|쪽지|카톡|링크|프로필)"
    r"|입장\s*(?:링크|하세요)",
    re.IGNORECASE,
)
_OFFER = re.compile(
    r"할인|무료|쿠폰|특가|최저가|정품|공구|판매|팝니다|팔아요|주문|구매|지급|적립|보너스|증정|부업|알바|일당"
    r"|월\s*\d|수익|대출|모집|후기|보장|반값|세일|상품권|현금|저렴|싸게"
)

# 홍보 신호 결합. 같은 문장에 '혜택·판매어 + 행동 유도 + (연락 경로 또는 금액·기한)'이 모두 있을 때만 홍보로 본다.
# 한 가지 신호는 정상 댓글에도 흔하므로('쿠폰 쓰고 주문했어요', '프로필 링크 잘 봤어요') 단독으로는 걸지 않는다.
_SIGNAL_OFFER = re.compile(
    _OFFER.pattern + r"|이벤트|포인트|체험|견적|혜택|추천인|리딩|시그널|입장\s*(?:코드|링크)|수강|클래스|무상|공짜",
)
_SIGNAL_CTA = re.compile(
    r"받아\s*가세요|받으세요|받아\s*보세요|참여\s*(?:하세요|하시면|해\s*보세요)|신청\s*(?:하세요|하시면|은|받)|지원\s*(?:은|는|하세요)"
    r"|(?:문의|상담)\s*(?:주세요|는|은|환영|바랍니다)|연락\s*(?:주세요|바랍니다|하세요)"
    r"|(?:쪽지|카톡|DM|디엠|톡)\s*(?:주세요|주시면|으로)|오세요|오시면|방문\s*(?:하세요|하시면)"
    r"|이용\s*(?:하세요|하시면)|확인\s*(?:하세요|바랍니다)|클릭|입장\s*(?:하세요|하시면)"
    r"|가입\s*(?:하세요|하시면|하면)|입력\s*(?:하세요|하면)|(?:구매|주문|예약|등록)\s*(?:하세요|하시면|하면|은|는)"
    r"|(?:링크|프로필)\s*참고|참고\s*(?:하세요|바랍니다)|들어오세요|놓치지\s*마세요|지금\s*바로|드려요|드립니다|해드려요",
    re.IGNORECASE,
)
_SIGNAL_CHANNEL = re.compile(r"프로필|링크|DM|디엠|쪽지|카톡|카카오톡|텔레|오픈\s*(?:채팅|카톡)|톡방", re.IGNORECASE)
_SIGNAL_MONEY = re.compile(r"월\s*\d+|\d[\d,]*\s*(?:%|퍼센트|원|만\s*원|천\s*원)|선착순|한정|마감\s*임박|즉시")
# 조건부 혜택·서비스 광고·위장 광고·운세 유인·채널 홍보처럼 한 문장 안의 고정된 판매자 말투.
_SELLER_PITCH = re.compile(
    r"(?:방문|오시|가입|구매|신청|참여|주문|예약)\s*하시면[^.!?\n]{0,25}?(?:무료|할인|쿠폰|증정|지급|드려요|드립니다|사은품)"
    r"|(?:입력|가입|추천|참여|신청)\s*(?:하시면|하면)[^.!?\n]{0,20}?(?:지급|증정|드려요|드립니다)"
    r"|(?:외주|대행|제작|디자인|번역|과외|레슨)\s*(?:을\s*)?(?:받습니다|받아요|해드려요|해드립니다|해드릴게요|구합니다)"
    r"|광고\s*(?:아닙니다|아님|아니에요|아니고)[^.!?\n]{0,30}?(?:구매|링크|프로필|후기)"
    r"|(?:운세|사주|타로)[^.!?\n]{0,12}?(?:봐\s*드|풀이\s*해\s*드)|생년월일\s*(?:남기|적어)"
    r"|(?:제|저희|내)\s*(?:채널|계정|블로그|페이지)[^.!?\n]{0,6}?(?:구경|놀러|방문|들러|구독)"
)
# 글자 사이에 공백·점을 끼운 우회 표기. 이런 문장은 구분 기호를 뺀 글자로도 신호를 찾는다.
_OBFUSCATED = re.compile(r"[가-힣][\s.·\-_/|*~]{1,2}[가-힣](?:[\s.·\-_/|*~]{1,2}[가-힣]){2,}")


def _promo_signals(sentence):
    """홍보 신호 조합이 성립하면 규칙 이름을 돌려준다."""
    texts = [sentence]
    if _OBFUSCATED.search(sentence):
        texts.append(_COMPACT.sub("", sentence))
    for text in texts:
        if _LURE.search(text) and _OFFER.search(text):
            return "promo"
        if _SELLER_PITCH.search(text):
            return "promo"
        if (
            _SIGNAL_OFFER.search(text)
            and _SIGNAL_CTA.search(text)
            and (_SIGNAL_CHANNEL.search(text) or _SIGNAL_MONEY.search(text))
        ):
            return "promo"
    return None


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


_SENTENCE_END = re.compile(r"[!?\n]+|\.(?=\s|$)")


def _sentences(text):
    return [part for part in _SENTENCE_END.split(text) if part.strip()]


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
    spam += [name for name in _match(COMPACT_CLAIM_RULES, _COMPACT.sub("", normalized)) if name not in spam]
    # 유도 표현과 짝을 이루는 규칙은 서로 무관한 문장끼리 묶이지 않도록 문장 단위로 본다.
    for sentence in _sentences(normalized):
        compact = _COMPACT.sub("", sentence)
        if _TOPIC_LURE.search(compact):
            spam += [name for name in _match(COMPACT_TOPIC_RULES, compact) if name not in spam]
        name = _promo_signals(sentence)
        if name and name not in spam:
            spam.append(name)
    if _is_flood(normalized):
        spam.append("flood")
    return PatternHits(spam=tuple(spam), privacy=tuple(_match(PRIVACY_RULES, normalized)))
