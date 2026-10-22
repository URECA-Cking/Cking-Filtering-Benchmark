import json
import unittest
from collections import defaultdict
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"


def load(name):
    with (DATA / name).open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


SCHEMA = json.loads((DATA / "comments.schema.json").read_text(encoding="utf-8"))
ALLOWED_FIELDS = set(SCHEMA["properties"])
REQUIRED_FIELDS = set(SCHEMA["required"])
CASE_TYPES = set(SCHEMA["properties"]["caseType"]["enum"])
CONTEXT_FIELDS = set(SCHEMA["properties"]["context"]["properties"])

ROWS = load("context_eval.jsonl")


class ContextEvalSetTest(unittest.TestCase):
    def test_스키마의_필수_필드가_있고_정의되지_않은_필드는_없다(self):
        for row in ROWS:
            self.assertTrue(REQUIRED_FIELDS <= set(row), row["id"])
            self.assertTrue(set(row) <= ALLOWED_FIELDS, f"{row['id']}: {set(row) - ALLOWED_FIELDS}")

    def test_id는_고유하고_문장은_1에서_500자다(self):
        self.assertEqual(len({row["id"] for row in ROWS}), len(ROWS))
        for row in ROWS:
            self.assertTrue(1 <= len(row["text"]) <= 500, row["id"])

    def test_최종_결과는_PASS_또는_BLOCK이다(self):
        # 이 세트는 최종 시스템 결과(PASS/BLOCK)로 라벨을 붙인다. 경계 사례는 borderline로 표시한다.
        for row in ROWS:
            self.assertIn(row["expectedAction"], {"PASS", "BLOCK"}, row["id"])
            if row["expectedAction"] == "PASS":
                self.assertEqual(row["categories"], ["NONE"], row["id"])
            else:
                self.assertNotIn("NONE", row["categories"], row["id"])

    def test_모든_문장이_사람_검수_전이다(self):
        self.assertEqual({row["reviewStatus"] for row in ROWS}, {"pending_human"})

    def test_유형은_정의된_값이고_8개_유형이_모두_있다(self):
        self.assertEqual({row["caseType"] for row in ROWS}, CASE_TYPES)

    def test_짝은_정상_하나와_위반_하나이고_같은_유형과_split에_있다(self):
        pairs = defaultdict(list)
        for row in ROWS:
            pairs[row["pairId"]].append(row)
        for pair_id, rows in pairs.items():
            self.assertEqual(len(rows), 2, pair_id)
            self.assertEqual(sorted(r["expectedAction"] for r in rows), ["BLOCK", "PASS"], pair_id)
            self.assertEqual(len({r["caseType"] for r in rows}), 1, pair_id)
            self.assertEqual(len({r["split"] for r in rows}), 1, f"{pair_id}: 짝이 두 split에 걸쳐 있다")
            self.assertEqual(len({r["contextNeeded"] for r in rows}), 1, pair_id)

    def test_split은_유형마다_개발용_4쌍_최종용_2쌍이다(self):
        counts = defaultdict(lambda: defaultdict(set))
        for row in ROWS:
            counts[row["caseType"]][row["split"]].add(row["pairId"])
        for case_type, splits in counts.items():
            self.assertEqual((len(splits["dev"]), len(splits["final"])), (4, 2), case_type)

    def test_문맥이_필요하면_context가_있고_필요_없으면_없다(self):
        for row in ROWS:
            if row["contextNeeded"]:
                self.assertIn("context", row, row["id"])
                self.assertTrue(set(row["context"]) <= CONTEXT_FIELDS, row["id"])
                self.assertTrue(row["context"].get("postText") or row["context"].get("previousComment"), row["id"])
            else:
                self.assertNotIn("context", row, row["id"])

    def test_규칙을_만든_이전_탐색_문장은_쓰지_않는다(self):
        previous = set()
        for name in ["samples.jsonl", "probes.jsonl", "probes_normalized.jsonl", "probes_profanity.jsonl"]:
            previous |= {row["text"] for row in load(name)}
        reused = [row["id"] for row in ROWS if row["text"] in previous]
        self.assertEqual(reused, [])

    def test_개인정보와_링크_예시는_가짜_값만_쓴다(self):
        # 이 세트에는 실제 연락처·링크를 넣지 않는다. 숫자 11자리나 http가 나오면 점검한다.
        for row in ROWS:
            self.assertNotIn("http", row["text"], row["id"])
            digits = "".join(ch for ch in row["text"] if ch.isdigit())
            self.assertLess(len(digits), 8, row["id"])


if __name__ == "__main__":
    unittest.main()
