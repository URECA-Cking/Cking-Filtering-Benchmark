import unittest

from src.pipeline import evaluate, to_record


def fake_model(flagged_texts=(), failing_texts=()):
    """주어진 문장에만 위반으로 판정하거나 실패하는 가짜 모델. 호출된 문장을 calls에 남긴다."""
    calls = []

    def call(text):
        calls.append(text)
        if text in failing_texts:
            return {"apiStatus": "error", "error": "http 500"}
        return {"apiStatus": "ok", "flagged": text in flagged_texts}

    call.calls = calls
    return call


class PipelineTest(unittest.TestCase):
    def test_self_harm_only_flag_does_not_block_an_out_of_scope_idiom(self):
        def model_call(_text):
            return {"apiStatus": "ok", "flagged": True, "flaggedCategories": ["self-harm"]}

        result = evaluate("죽는 줄 알았네 너무 웃겨서 ㅋㅋㅋㅋ", model_call)
        self.assertTrue(result.model_original["flagged"])
        self.assertFalse(result.model_flagged)
        self.assertEqual(result.decision.action, "PASS")

    def test_self_harm_with_violence_still_blocks(self):
        def model_call(_text):
            return {"apiStatus": "ok", "flagged": True,
                    "flaggedCategories": ["self-harm", "violence"]}

        result = evaluate("가만 안 있을 거야", model_call)
        self.assertTrue(result.model_flagged)
        self.assertEqual(result.decision.action, "BLOCK")

    def test_정규화로_문장이_바뀌면_원문과_정규화본을_모두_모델에_보낸다(self):
        model = fake_model()
        evaluate("ㅂㅅ같은 편집이네", model)
        self.assertEqual(model.calls, ["ㅂㅅ같은 편집이네", "병신같은 편집이네"])

    def test_정규화로_바뀌지_않으면_모델은_한_번만_호출한다(self):
        model = fake_model()
        result = evaluate("편집이 너무 느려서 지루했어요", model)
        self.assertEqual(len(model.calls), 1)
        self.assertIsNone(result.model_normalized)

    def test_정규화본에서만_모델이_걸려도_막는다(self):
        model = fake_model(flagged_texts={"꺼져 쓰레기야"})
        result = evaluate("ㄲㅈ 쓰레기야", model)
        self.assertFalse(result.model_original["flagged"])
        self.assertTrue(result.model_flagged)
        self.assertEqual(result.decision.action, "BLOCK")
        self.assertIn("model", result.decision.reasons)

    def test_욕설_사전에만_걸려도_막는다(self):
        result = evaluate("시발 감동적이다 진짜 눈물 났어요", fake_model())
        self.assertEqual(result.decision.action, "BLOCK")
        self.assertEqual(result.decision.reasons, ("profanity:시발",))

    def test_변형_표기도_정규화한_문장으로_욕설_사전에_걸린다(self):
        result = evaluate("ㅅㅂ 개웃기네 ㅋㅋㅋ", fake_model())
        self.assertEqual(result.decision.reasons, ("profanity:시발",))

    def test_개인정보와_스팸은_모델_없이도_막는다(self):
        self.assertEqual(evaluate("010-0000-1111로 연락주세요", fake_model()).decision.reasons, ("privacy:phone",))
        result = evaluate("지금 가입하면 수익 보장 http://example.invalid/join", fake_model())
        self.assertEqual(result.decision.action, "BLOCK")

    def test_감탄으로_쓰는_말과_정상_문장은_통과한다(self):
        for text in ["미친 이거 너무 웃기다", "존나 재밌다 이거", "개웃기네 ㅋㅋㅋ", "이 영상이 제 시발점이 됐어요"]:
            self.assertEqual(evaluate(text, fake_model()).decision.action, "PASS", text)

    def test_모델_호출이_실패하면_상태를_남기고_규칙만으로_판정한다(self):
        model = fake_model(failing_texts={"편집이 너무 느려서 지루했어요"})
        result = evaluate("편집이 너무 느려서 지루했어요", model)
        self.assertEqual(result.model_status, "error")
        self.assertFalse(result.model_flagged)
        self.assertEqual(result.decision.action, "PASS")
        # 실패해도 규칙 신호가 있으면 막는다
        blocked = evaluate("010-0000-1111", fake_model(failing_texts={"010-0000-1111"}))
        self.assertEqual((blocked.model_status, blocked.decision.action), ("error", "BLOCK"))

    def test_기록에는_모델_점수_규칙_신호_최종_판정이_따로_담긴다(self):
        record = to_record(evaluate("ㅂㅅ같은 편집이네", fake_model(flagged_texts={"병신같은 편집이네"})))
        self.assertEqual(set(record), {"modelStatus", "model", "rules", "final"})
        self.assertTrue(record["model"]["flagged"])
        self.assertEqual(record["rules"]["normalizedText"], "병신같은 편집이네")
        self.assertEqual(record["rules"]["normalizationApplied"], ["initial"])
        self.assertEqual(record["rules"]["profanity"], ["병신"])
        self.assertEqual(record["final"], {"action": "BLOCK", "reasons": ["model", "profanity:병신"]})


if __name__ == "__main__":
    unittest.main()
