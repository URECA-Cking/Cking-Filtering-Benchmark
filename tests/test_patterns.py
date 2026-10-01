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
