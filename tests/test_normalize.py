import unittest

from src.rules.normalize import normalize


class NormalizeTest(unittest.TestCase):
    def assert_normalized(self, text, expected, applied):
        result = normalize(text)
        self.assertEqual(result.text, expected)
        self.assertEqual(result.applied, applied)
        self.assertEqual(result.original, text)

    def test_초성_약어를_표준_표기로_바꾼다(self):
        self.assert_normalized("ㅂㅅ같은 편집이네", "병신같은 편집이네", ("initial",))
        self.assert_normalized("ㅈㄹ하네 진짜", "지랄하네 진짜", ("initial",))
        self.assert_normalized("ㄲㅈ 쓰레기야", "꺼져 쓰레기야", ("initial",))
        self.assert_normalized("ㅅㅂ 개웃기네 ㅋㅋㅋ", "시발 개웃기네 ㅋㅋㅋ", ("initial",))

    def test_합친_자모와_다른_초성_욕설도_바꾼다(self):
        self.assert_normalized("ㅄ같은 편집이네", "병신같은 편집이네", ("initial",))
        self.assert_normalized("ㅁㅊ 이거 너무 웃기다", "미친 이거 너무 웃기다", ("initial",))
        self.assert_normalized("ㅈㄴ 재밌다", "존나 재밌다", ("initial",))
        self.assert_normalized("ㅅㄲ야 영상 내려", "새끼야 영상 내려", ("initial",))
        self.assert_normalized("ㄷㅊ 좀", "닥쳐 좀", ("initial",))
        self.assert_normalized("ㅈㄹㄴ 별로네", "지랄 별로네", ("initial",))

    def test_글자_분리_표기를_표준_표기로_바꾼다(self):
        self.assert_normalized("씨ㅂ럴 놈아 영상이 왜 이래", "씨발 놈아 영상이 왜 이래", ("split",))

    def test_모음을_늘린_표기를_표준_표기로_바꾼다(self):
        self.assert_normalized("씨이이발 너 때문에 짜증나", "씨발 너 때문에 짜증나", ("stretched",))
        self.assert_normalized("시으으발 뭐야", "시발 뭐야", ("stretched",))

    def test_초성은_다른_자모와_붙어_있으면_바꾸지_않는다(self):
        # ㅋㅋㅋ, ㅠㅠ 같은 자모 표기와 섞이지 않는지 확인한다.
        for text in ["ㅋㅋㅋ 재밌다", "ㅠㅠ 감동", "ㅂㅅㅅ", "ㅄㅄ", "ㅁㅊㅋ"]:
            self.assertFalse(normalize(text).changed, text)

    def test_분류기가_이미_처리하는_표기는_바꾸지_않는다(self):
        for text in [
            "ㅅㅣ발 너 영상 뭐하는 거냐",  # 자모 분리
            "병.신 같은 놈이 영상을 올리네",  # 특수문자 삽입
            "시1발 너 진짜 별로다",  # 숫자 삽입
        ]:
            self.assertFalse(normalize(text).changed, text)

    def test_정상_문장은_바꾸지_않는다(self):
        for text in [
            "이 영상이 제 공부의 시발점이 됐어요 감사합니다",
            "개발 공부하는 분들께 도움이 되는 영상이네요",
            "죽는 줄 알았네 너무 웃겨서 ㅋㅋㅋㅋ",
            "이 이야기 정말 재밌어요 이이야기",
            "편집이 너무 느려서 지루했어요",
            "",
        ]:
            self.assertFalse(normalize(text).changed, text)

    def test_영문_자판과_공백_삽입은_범위에서_제외한다(self):
        # 표준 표기로 바꿔도 분류기 점수가 오르지 않았다(이슈 #8 탐색).
        for text in ["tlqkf 너 영상 이게 뭐냐", "시 발 너 뭐하는 거냐 이게"]:
            self.assertFalse(normalize(text).changed, text)

    def test_여러_규칙이_함께_적용된다(self):
        result = normalize("ㅂㅅ 씨이이발 진짜")
        self.assertEqual(result.text, "병신 씨발 진짜")
        self.assertEqual(result.applied, ("initial", "stretched"))


if __name__ == "__main__":
    unittest.main()
