import json
import unittest
from pathlib import Path

from src.rules.normalize import normalize
from src.rules.profanity import analyze_profanity

DATA = Path(__file__).resolve().parent.parent / "data"
DATA_FILES = ["samples.jsonl", "probes.jsonl", "probes_normalized.jsonl", "probes_profanity.jsonl"]


def words(text):
    return analyze_profanity(text).words


class ProfanityTest(unittest.TestCase):
    def test_감탄으로도_쓸_수_없는_욕설은_단독으로도_걸린다(self):
        for text, expected in [
            ("시발", ("시발",)),
            ("아 씨발 진짜", ("시발",)),
            ("지랄하네", ("지랄",)),
            ("병신같은 편집", ("병신",)),
            ("시발 병신아", ("시발", "병신")),
        ]:
            self.assertEqual(words(text), expected, text)

    def test_새끼는_욕설로_쓰인_형태만_잡는다(self):
        self.assertEqual(words("개새끼야"), ("새끼",))
        self.assertEqual(words("미친 새끼 같으니"), ("새끼",))
        self.assertEqual(words("그 새끼들아 조용히 해"), ("새끼",))

    def test_감탄으로_쓰는_말은_사전에_없어_걸리지_않는다(self):
        for text in ["미친 이거 너무 웃기다", "존나 재밌다 이거", "개웃기네 ㅋㅋㅋ", "아 진짜 개쩐다 레전드"]:
            self.assertEqual(words(text), (), text)

    def test_정상_단어는_걸리지_않는다(self):
        for text in [
            "이 영상이 제 공부의 시발점이 됐어요 감사합니다",
            "2016년은 병신년이었다",
            "새끼 고양이가 너무 귀여워요",
            "새끼손가락을 걸고 약속해요",
            "개발 공부하는 분들께 도움이 되는 영상이네요",
        ]:
            self.assertEqual(words(text), (), text)

    def test_시발점심처럼_점으로_시작하는_다른_말은_욕설로_본다(self):
        self.assertEqual(words("시발점심 뭐 먹지"), ("시발",))

    def test_예외는_팬_댓글에_나올_법한_단어로_한정한다(self):
        # 걸려도 HOLD(사람 확인)라 비용이 작다. 실제 데이터에서 오탐이 확인될 때 예외를 늘린다.
        self.assertEqual(words("시발역에서 출발합니다"), ("시발",))
        self.assertEqual(words("지랄탄이 최루탄의 다른 이름이래요"), ("지랄",))
        self.assertEqual(words("시발 점 하나 찍었다"), ("시발",))

    def test_정규화한_문장을_넘기면_변형_표기도_잡는다(self):
        for text, expected in [
            ("ㅅㅂ 개웃기네", ("시발",)),
            ("ㅂㅅ같은 편집이네", ("병신",)),
            ("씨ㅂ럴 놈아", ("시발",)),
            ("씨이이발 너 때문에", ("시발",)),
            ("ㅅㄲ야 영상 내려", ("새끼",)),
        ]:
            self.assertEqual(words(normalize(text).text), expected, text)

    def test_정규화하지_않은_변형_표기는_걸리지_않는다(self):
        # 사전은 표준 표기만 본다. 변형 표기는 normalize를 거쳐 넘긴다.
        self.assertEqual(words("ㅅㅂ"), ())


class DatasetTest(unittest.TestCase):
    """이슈 #6·#8 탐색 데이터에서 사전에 있는 욕설이 들어 있는 문장만 걸리는지 확인한다."""

    LITERALS = ["시발", "씨발", "지랄", "병신"]
    EXCEPTIONS = ["시발점", "병신년"]

    def test_사전_단어가_있을_때만_걸린다(self):
        rows = []
        for name in DATA_FILES:
            with (DATA / name).open(encoding="utf-8") as f:
                rows += [json.loads(line) for line in f if line.strip()]
        for row in rows:
            text = normalize(row["text"]).text
            checked = text
            for exception in self.EXCEPTIONS:
                checked = checked.replace(exception, "")
            expected = any(literal in checked for literal in self.LITERALS) or "새끼" in checked
            self.assertEqual(analyze_profanity(text).hit, expected, f"{row['id']}: {row['text']}")


if __name__ == "__main__":
    unittest.main()
