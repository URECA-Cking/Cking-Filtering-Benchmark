import unittest

from src.local_pipeline import LocalFilter, evaluate_local, to_record


def fake_score(score=0.0, scores=None):
    """주어진 점수를 돌려주는 가짜 모델. 호출된 문장을 calls에 남긴다."""
    calls = []

    def call(text):
        calls.append(text)
        return (scores or {}).get(text, score)

    call.calls = calls
    return call


class LocalPipelineTest(unittest.TestCase):
    def test_아무_신호도_없으면_통과한다(self):
        result = evaluate_local("오늘 영상 너무 좋았어요", fake_score(0.01))
        self.assertEqual(result.decision.action, "PASS")
        self.assertEqual(result.decision.reasons, ())

    def test_점수가_임계값_이상이면_막고_근거는_classifier다(self):
        result = evaluate_local("아무 문장", fake_score(0.97))
        self.assertEqual((result.decision.action, result.decision.reasons), ("BLOCK", ("classifier",)))

    def test_임계값과_같은_점수도_막는다(self):
        self.assertEqual(evaluate_local("문장", fake_score(0.95)).decision.action, "BLOCK")
        self.assertEqual(evaluate_local("문장", fake_score(0.9499)).decision.action, "PASS")

    def test_임계값을_바꿀_수_있다(self):
        self.assertEqual(evaluate_local("문장", fake_score(0.6), threshold=0.5).decision.action, "BLOCK")
        self.assertEqual(evaluate_local("문장", fake_score(0.6), threshold=0.9).decision.action, "PASS")

    def test_모델_점수가_낮아도_개인정보_규칙에_걸리면_막는다(self):
        result = evaluate_local("실제 번호래요 010-0000-1111 전화해보세요", fake_score(0.0))
        self.assertEqual(result.decision.action, "BLOCK")
        self.assertEqual(result.decision.reasons, ("privacy:phone",))

    def test_모델_점수가_낮아도_스팸_문구에_걸리면_막는다(self):
        result = evaluate_local("수익 보장 지금 가입하세요", fake_score(0.0))
        self.assertEqual((result.decision.action, result.decision.reasons), ("BLOCK", ("spam:solicit",)))

    def test_링크만_있으면_막지_않는다(self):
        result = evaluate_local("공식 공지는 example.com/notice 에 있어요", fake_score(0.0))
        self.assertEqual(result.patterns.spam, ("link",))
        self.assertEqual(result.decision.action, "PASS")

    def test_변형_표기는_정규화본으로_욕설_사전을_검사한다(self):
        result = evaluate_local("ㅅㅂ", fake_score(0.0))
        self.assertEqual(result.normalization.text, "시발")
        self.assertEqual((result.decision.action, result.decision.reasons), ("BLOCK", ("profanity:시발",)))

    def test_허용하는_감탄은_점수가_낮으면_통과한다(self):
        self.assertEqual(evaluate_local("미친 이거 실화냐 ㅋㅋㅋ", fake_score(0.02)).decision.action, "PASS")

    def test_모델에는_원문만_한_번_보낸다(self):
        score = fake_score(0.0)
        evaluate_local("ㅅㅂ", score)
        self.assertEqual(score.calls, ["ㅅㅂ"])

    def test_모델과_규칙이_함께_막으면_근거를_모두_남긴다(self):
        result = evaluate_local("병신 번호 010-0000-1111", fake_score(0.99))
        self.assertEqual(result.decision.reasons, ("classifier", "profanity:병신", "privacy:phone"))

    def test_점수를_구하지_못하면_예외를_그대로_올린다(self):
        def failing(_text):
            raise RuntimeError("model unavailable")

        with self.assertRaises(RuntimeError):
            evaluate_local("문장", failing)

    def test_NaN_무한대_범위_밖_점수는_통과시키지_않고_거부한다(self):
        # 규칙에 걸리지 않는 댓글이라 점수가 비정상이면 조용히 PASS되기 쉬운 경우다.
        for bad in (float("nan"), float("inf"), float("-inf"), -0.1, 1.5):
            with self.subTest(score=bad):
                with self.assertRaises(ValueError):
                    evaluate_local("오늘 영상 너무 좋았어요", fake_score(bad))

    def test_숫자로_바꿀_수_없는_점수는_거부한다(self):
        for bad in (None, "높음"):
            with self.subTest(score=bad):
                with self.assertRaises((TypeError, ValueError)):
                    evaluate_local("오늘 영상 너무 좋았어요", fake_score(bad))

    def test_0과_1은_유효한_점수다(self):
        self.assertEqual(evaluate_local("문장", fake_score(0.0)).decision.action, "PASS")
        self.assertEqual(evaluate_local("문장", fake_score(1.0)).decision.action, "BLOCK")

    def test_비정상_점수는_규칙에_걸리는_댓글도_거부한다(self):
        # 점수를 믿을 수 없으면 규칙 결과와 상관없이 호출한 쪽이 실패를 알아야 한다.
        with self.assertRaises(ValueError):
            evaluate_local("수익 보장 지금 가입하세요", fake_score(float("nan")))

    def test_진입점도_비정상_점수를_예외로_올린다(self):
        moderator = LocalFilter(score_fn=fake_score(float("nan")))
        with self.assertRaises(ValueError):
            moderator.moderate("평범한 문장")

    def test_기록에는_모델_점수와_규칙_신호가_따로_담긴다(self):
        record = to_record(evaluate_local("수익 보장 ㅅㅂ", fake_score(0.4)))
        self.assertEqual(record["final"], {"action": "BLOCK", "reasons": ["profanity:시발", "spam:solicit"]})
        self.assertEqual(record["model"], {"score": 0.4, "threshold": 0.95, "flagged": False})
        self.assertEqual(record["rules"]["normalizedText"], "수익 보장 시발")
        self.assertEqual(record["rules"]["normalizationApplied"], ["initial"])
        self.assertEqual(record["rules"]["spam"], ["solicit"])
        self.assertEqual(record["rules"]["profanity"], ["시발"])

    def test_정규화로_바뀌지_않으면_정규화본을_기록하지_않는다(self):
        record = to_record(evaluate_local("좋은 영상이네요", fake_score(0.0)))
        self.assertIsNone(record["rules"]["normalizedText"])
        self.assertEqual(record["rules"]["normalizationApplied"], [])

    def test_진입점은_점수_함수를_주입해_시험할_수_있다(self):
        moderator = LocalFilter(score_fn=fake_score(scores={"위험한 문장": 0.99}))
        self.assertEqual(moderator.moderate("위험한 문장")["final"]["action"], "BLOCK")
        self.assertEqual(moderator.moderate("평범한 문장")["final"]["action"], "PASS")

    def test_임계값이_범위를_벗어나면_거부한다(self):
        for threshold in (-0.1, 1.5):
            with self.assertRaises(ValueError):
                LocalFilter(threshold=threshold, score_fn=fake_score())


if __name__ == "__main__":
    unittest.main()
