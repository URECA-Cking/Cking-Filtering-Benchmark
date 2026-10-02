import json
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
ROWS = [json.loads(line) for line in (ROOT / "data" / "realistic_comments.jsonl").read_text(encoding="utf-8").splitlines()]
SCHEMA = json.loads((ROOT / "data" / "comments.schema.json").read_text(encoding="utf-8"))


class RealisticSetTest(unittest.TestCase):
    def test_dataset_has_distinct_valid_rows(self):
        self.assertEqual(len(ROWS), 60)
        self.assertEqual(len({row["id"] for row in ROWS}), len(ROWS))
        for row in ROWS:
            self.assertTrue(set(SCHEMA["required"]) <= set(row), row["id"])
            self.assertTrue(set(row) <= set(SCHEMA["properties"]), row["id"])
            self.assertTrue(1 <= len(row["text"]) <= 500, row["id"])
            self.assertEqual(row["source"], "synthetic", row["id"])
            self.assertEqual(row["reviewStatus"], "pending_human", row["id"])
            self.assertIn(row["platform"], {"instagram", "youtube", "facebook"})
            self.assertIn(row["split"], {"dev", "final"})
            self.assertIn(row["expectedAction"], {"PASS", "BLOCK"})
            self.assertEqual(row["categories"] == ["NONE"], row["expectedAction"] == "PASS", row["id"])

    def test_each_platform_has_normal_comments_and_reserved_final_rows(self):
        counts = Counter((row["platform"], row["split"], row["expectedAction"]) for row in ROWS)
        for platform in ("instagram", "youtube", "facebook"):
            self.assertEqual(counts[platform, "dev", "PASS"], 12)
            self.assertEqual(counts[platform, "dev", "BLOCK"], 3)
            self.assertEqual(counts[platform, "final", "PASS"], 4)
            self.assertEqual(counts[platform, "final", "BLOCK"], 1)


if __name__ == "__main__":
    unittest.main()
