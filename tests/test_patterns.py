import json
import unittest
from pathlib import Path

from src.rules.patterns import analyze_patterns

DATA = Path(__file__).resolve().parent.parent / "data"
DATA_FILES = ["samples.jsonl", "probes.jsonl", "probes_normalized.jsonl", "probes_profanity.jsonl"]


def load_rows():
    rows = []
    for name in DATA_FILES:
        with (DATA / name).open(encoding="utf-8") as f:
            rows += [json.loads(line) for line in f if line.strip()]
    return rows


class PrivacyTest(unittest.TestCase):
    def privacy(self, text):
        return analyze_patterns(text).privacy

    def test_휴대전화_번호를_여러_표기로_잡는다(self):
        for text in [
            "연락처는 010-1234-5678 입니다",
            "01012345678로 연락주세요",
            "010 1234 5678 번호예요",
            "010.1234.5678",
            "０１０-１２３４-５６７８",  # 전각 숫자
            "공일공 일이삼사 오육칠팔",
        ]:
            self.assertIn("phone", self.privacy(text), text)

    def test_유선전화는_구분_기호가_있을_때만_잡는다(self):
        self.assertIn("phone", self.privacy("가게 번호 02-123-4567"))
        self.assertNotIn("phone", self.privacy("조회수 021234567회 돌파"))

    def test_전화번호가_아닌_숫자는_잡지_않는다(self):
        for text in ["2026년 10월 1일 업로드", "조회수 12345678회 돌파", "1234-5678 다음 화", "구독자 3만 명"]:
            self.assertEqual(self.privacy(text), (), text)

    def test_이메일을_잡는다(self):
        self.assertIn("email", self.privacy("메일은 example.user+test@example.com 으로 보내주세요"))
        self.assertEqual(self.privacy("@핸들만 있고 메일은 아님"), ())

    def test_주민등록번호_형식은_생년월일이_가능할_때만_잡는다(self):
        self.assertIn("rrn", self.privacy("900101-1234567"))
        self.assertIn("rrn", self.privacy("9001011234567"))
        self.assertNotIn("rrn", self.privacy("901301-1234567"))  # 13월

    def test_메신저_계정_안내를_잡는다(self):
        self.assertIn("account", self.privacy("제 카카오톡 아이디는 example_user_00 이에요"))
        self.assertIn("account", self.privacy("인스타 계정 example.user99 팔로우 해주세요"))
        self.assertEqual(self.privacy("카카오톡으로 영상 공유했어요"), ())

    def test_도로명_주소는_번지까지_있을_때만_잡는다(self):
        self.assertIn("address", self.privacy("서울시 예시구 가상로 0번길 에 사시는 분이죠"))
        self.assertEqual(self.privacy("서울시 강남구 테헤란로 맛집 소개해 주세요"), ())


class SpamTest(unittest.TestCase):
    def spam(self, text):
        return analyze_patterns(text).spam

    def test_링크를_잡는다(self):
        for text in [
            "여기 http://example.invalid/join 눌러보세요",
            "www.example.invalid 참고",
            "t.me/example_invalid 선착순",
            "naver.com 에서 봤어요",
        ]:
            self.assertIn("link", self.spam(text), text)

    def test_링크가_아닌_점이_있는_문장은_잡지_않는다(self):
        for text in ["영상 1.5배속으로 봤어요", "v1.0 업데이트 기다립니다", "그래서요... 어떻게 됐어요", "감사합니다.좋은 영상이네요"]:
            self.assertNotIn("link", self.spam(text), text)

    def test_금전_가입_유도_문구를_잡는다(self):
        self.assertIn("solicit", self.spam("지금 가입하면 수익 보장"))
        self.assertIn("solicit", self.spam("무료 코인 받아가세요"))
        self.assertEqual(self.spam("선착순 이벤트 참여했어요"), ())

    def test_맞구독_요청을_잡는다(self):
        self.assertIn("engagement_bait", self.spam("첫 구독자 이벤트 구독 좋아요 알림 부탁드려요 맞구독 해요"))

    def test_투자_부업_유도_문구를_잡는다(self):
        for text in [
            "무료 주식 리딩방 입장하세요",
            "코인 시그널방 운영 중입니다",
            "이번 달 수익률 150% 인증합니다",
            "원금 보장 확정 수익 상품입니다 문의 주세요",
            "집에서 한 달에 200 버는 법 공유해요",
            "하루 일당 10만원 가능합니다 지금 지원하세요",
        ]:
            self.assertIn("invest", self.spam(text), text)

    def test_투자_표현이_들어간_정상_댓글은_잡지_않는다(self):
        for text in [
            "투자 영상 잘 봤어요 공부가 많이 됐어요",
            "원금 보장은 안 되는 상품이라고 하셨죠",
            "수익 공개 영상 재밌게 봤어요",
            "부업으로 영상 편집을 시작했어요",
            "일당 10만원이라니 영상 속 알바 후기 놀랍네요",
        ]:
            self.assertNotIn("invest", self.spam(text), text)

    def test_투자_도박_주제어는_유도_표현과_함께_있을_때만_잡는다(self):
        self.assertIn("invest", self.spam("리딩방 사기 조심하세요 가입 문의는 카톡으로"))
        self.assertIn("invest", self.spam("고수익 보장 상담 신청받습니다"))
        self.assertIn("invest", self.spam("신용불량자도 당일대출 가능합니다"))
        self.assertIn("gambling", self.spam("먹튀 없는 바카라 사이트 가입 링크 드려요"))
        for text in ["리딩방", "고수익", "신용불량", "바카라", "먹튀"]:
            self.assertEqual(self.spam(text), (), text)

    def test_경고와_피해_경험_댓글은_투자_도박_규칙에_걸리지_않는다(self):
        for text in [
            "리딩방 사기 조심하세요",
            "고수익 광고 믿지 마세요",
            "먹튀 피해 예방 영상 감사합니다",
            "신용불량자 대출 사기 조심하세요",
            "바카라 중독 위험하니 절대 하지 마세요",
            "리딩방에서 손실 봤어요 다들 조심하세요",
            "토토사이트 먹튀 당해서 돈 날렸어요 ㅠㅠ",
            "고수익 보장은 불가능합니다 속지 마세요",
        ]:
            hits = self.spam(text)
            self.assertNotIn("invest", hits, text)
            self.assertNotIn("gambling", hits, text)

    def test_도박_사이트_유도를_잡고_영화_이야기는_잡지_않는다(self):
        for text in ["바카라 필승 전략 알려드려요", "스포츠토토 사이트 추천해요", "신규가입 보너스 드립니다 온라인 카지노"]:
            self.assertIn("gambling", self.spam(text), text)
        for text in ["영화 카지노 명작이죠", "토토로 같이 봐요", "스포츠 토토 뉴스가 나와서 놀랐어요"]:
            self.assertNotIn("gambling", self.spam(text), text)

    def test_구분_기호를_끼운_우회_표기도_잡는다(self):
        self.assertIn("invest", self.spam("고 수 익 보장 부업 모집"))
        self.assertIn("invest", self.spam("리.딩.방 입장 안내"))

    def test_팔로워_판매를_잡고_질문은_잡지_않는다(self):
        self.assertIn("follower_sale", self.spam("팔로워 늘려드려요 가격 저렴해요"))
        self.assertIn("follower_sale", self.spam("조회수 5천 3만원에 해드립니다"))
        for text in ["팔로워 늘리는 법 알려주세요", "좋아요 눌렀어요 구독도 했어요", "팔로워 수가 많이 늘었네요"]:
            self.assertNotIn("follower_sale", self.spam(text), text)

    def test_판매자_말투를_잡고_팬_댓글은_잡지_않는다(self):
        for text in ["중고 키보드 싸게 팝니다", "이번 공구 오픈했어요", "굿즈 판매합니다"]:
            self.assertIn("sale", self.spam(text), text)
        for text in ["공구 오픈하면 알려주세요", "팬미팅 현장 판매 굿즈 줄이 길었어요", "판매 중인 걸로 알아요"]:
            self.assertNotIn("sale", self.spam(text), text)

    def test_유도_말투와_혜택_단어가_함께_있을_때만_홍보로_본다(self):
        self.assertIn("promo", self.spam("할인 쿠폰 드려요 프로필 링크 확인하세요"))
        self.assertIn("promo", self.spam("무료 상담 신청은 DM 주세요"))
        for text in [
            "굿즈 할인 언제 하나요? 영상 링크 확인하세요.",
            "쿠폰 받았어요. 프로필 링크 확인하세요 영상 재밌어요",
            "굿즈 할인 언제 해요?",
            "협업 문의는 DM으로 주시면 돼요",
            "할인 이벤트 하는 거 맞죠? 링크 확인해 보겠습니다",
            "링크 확인했는데 영상이 안 열려요",
            "쿠폰 쓰고 주문했는데 배송이 빨라요",
        ]:
            self.assertNotIn("promo", self.spam(text), text)

    def test_링크는_혜택_단어가_함께_있을_때만_홍보로_본다(self):
        self.assertIn("link_promo", self.spam("포인트 지급 이벤트 진행 중 example.com/join"))
        self.assertIn("link_promo", self.spam("무료 체험 신청 http://example.invalid/free"))
        for text in ["출처는 example.com/news 입니다 참고하세요", "참고 영상 youtu.be/example 보시면 이해돼요"]:
            self.assertNotIn("link_promo", self.spam(text), text)

    def test_혜택_행동유도_연락경로가_한_문장에_모일_때만_홍보로_본다(self):
        self.assertIn("promo", self.spam("오픈 기념 전 메뉴 20% 할인 방문하시면 음료 드려요"))
        self.assertIn("promo", self.spam("체험단 모집 무료 제공 원하시면 카톡 주세요"))
        for text in [
            "오늘 프로필 링크에서 30% 할인 쿠폰 받았어요 감사합니다",
            "쿠폰 쓰고 주문했는데 포장이 꼼꼼해요",
            "세일 기간에 샀는데 후기 보니 잘 산 것 같아요",
            "이벤트 응모했는데 당첨되면 좋겠다",
        ]:
            self.assertNotIn("promo", self.spam(text), text)

    def test_글자_사이에_기호를_끼운_홍보도_잡는다(self):
        self.assertIn("promo", self.spam("카 톡 으 로 오 시 면 무 료 쿠 폰 드 려 요"))

    def test_맞팔_푸념은_잡지_않고_요청은_잡는다(self):
        self.assertIn("engagement_bait", self.spam("맞팔 하실 분 댓글 남겨 주세요"))
        self.assertNotIn("engagement_bait", self.spam("맞팔 요청이 너무 많이 와서 곤란해요"))

    def test_팔로워_대량_증가_서비스를_잡는다(self):
        self.assertIn("follower_sale", self.spam("인스타 팔로워 대량 증가 서비스 합니다"))
        self.assertNotIn("follower_sale", self.spam("팔로워 늘리는 방법 영상 또 올려주세요"))

    def test_판매자_말투_광고를_잡는다(self):
        for text in [
            "방문하시면 커피 한 잔 무료로 드려요",
            "로고 디자인 외주 받습니다 가격은 상의해요",
            "광고 아닙니다 직접 써본 후기예요 구매는 프로필",
            "무료 타로 봐드려요 이름과 생년월일 남기세요",
            "저희 채널도 놀러오세요 구독하면 맞구독 갑니다",
            "맞팔 선팔 환영해요 서로 소통해요",
        ]:
            self.assertTrue(self.spam(text), text)
        for text in ["광고 아닌 척하는 영상이 너무 많아요", "번역 외주 알아보는 중인데 추천해 주세요", "제 채널은 아니지만 이 영상 추천해요"]:
            self.assertEqual(self.spam(text), (), text)

    # 알려진 오탐. 정책이 정해지거나 규칙을 고치면 expectedFailure를 떼고 일반 테스트로 바꾼다.
    @unittest.expectedFailure
    def test_알려진_오탐_경고문의_주제어와_링크_표현(self):
        self.assertNotIn("invest", self.spam("리딩방 링크 누르지 마세요"))

    @unittest.expectedFailure
    def test_알려진_오탐_무료_자료_공유_링크(self):
        self.assertNotIn("link_promo", self.spam("무료 강의 자료 공유해요 example.com/pdf"))

    def test_같은_구절_도배를_잡는다(self):
        self.assertIn("flood", self.spam("구독 좋아요 구독 좋아요 구독 좋아요 구독 좋아요"))
        self.assertIn("flood", self.spam("이벤트참여 이벤트참여 이벤트참여 이벤트참여"))

    def test_웃음과_짧은_반복은_도배로_보지_않는다(self):
        for text in ["ㅋㅋㅋ ㅋㅋㅋ ㅋㅋㅋ ㅋㅋㅋ 너무 웃겨요", "정말 정말 정말 정말 재밌다", "와 와 와 와 대박"]:
            self.assertNotIn("flood", self.spam(text), text)


class DatasetTest(unittest.TestCase):
    """이슈 #6·#8 탐색 데이터로 오탐과 미탐을 확인한다."""

    def test_스팸_개인정보가_아닌_문장은_하나도_걸리지_않는다(self):
        for row in load_rows():
            if {"SPAM", "PRIVACY"} & set(row["categories"]):
                continue
            hits = analyze_patterns(row["text"])
            self.assertFalse(hits.spam_hit or hits.privacy_hit, f"{row['id']}: {row['text']} -> {hits}")

    def test_일상_댓글_평가_세트의_정상_문장은_스팸_규칙에_걸리지_않는다(self):
        checked = 0
        for name in ("realistic_comments.jsonl", "context_eval.jsonl"):
            with (DATA / name).open(encoding="utf-8") as f:
                for line in f:
                    row = json.loads(line) if line.strip() else None
                    if row and row["expectedAction"] == "PASS":
                        names = [x for x in analyze_patterns(row["text"]).spam if x != "link"]
                        self.assertEqual(names, [], f"{row['id']}: {row['text']}")
                        checked += 1
        self.assertGreaterEqual(checked, 50)

    def test_정답이_BLOCK인_스팸_개인정보_문장은_모두_걸린다(self):
        checked = 0
        for row in load_rows():
            if row["expectedAction"] == "BLOCK" and {"SPAM", "PRIVACY"} & set(row["categories"]):
                hits = analyze_patterns(row["text"])
                self.assertTrue(hits.spam_hit or hits.privacy_hit, f"{row['id']}: {row['text']}")
                checked += 1
        self.assertGreaterEqual(checked, 5)


if __name__ == "__main__":
    unittest.main()
