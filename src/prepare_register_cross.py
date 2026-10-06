"""Export register-crossed training pairs: formal-speech threats vs casual benign comments.

Complements the casual-threat / formal-benign data that dominates earlier sets so
speech register no longer predicts the label. Rejects texts too similar to any
earlier training or evaluation set, including threat_eval_v3_register, which
must never enter training. Labels are Codex-provisional, not human approved.
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from src.prepare_stalking_warning import prepare
from src.prepare_threat_context import ROOT, write
from src.validate_dktc_review_sheet import normalized


SOURCE = ROOT / "data/restricted/register_cross_v1.tsv"
OUTPUT = ROOT / "data/restricted/register_cross_v1_train.jsonl"
PRIOR = [
    ROOT / "data/context_eval.jsonl",
    ROOT / "data/realistic_comments.jsonl",
    ROOT / "data/restricted/gap_challenge_v1.jsonl",
    ROOT / "data/restricted/dktc/provisional_comments.jsonl",
    ROOT / "data/restricted/threat_context_v1_train.jsonl",
    ROOT / "data/restricted/threat_context_v1_heldout.jsonl",
    ROOT / "data/restricted/stalking_warning_v1_train.jsonl",
    ROOT / "data/restricted/threat_eval_v2.jsonl",
    ROOT / "data/restricted/threat_eval_v3_register.jsonl",
]


def load_prior():
    texts = []
    for path in PRIOR:
        if not path.exists():
            raise FileNotFoundError(f"Missing earlier set for overlap check: {path}")
        with path.open(encoding="utf-8") as stream:
            texts.extend(normalized(json.loads(line)["text"]) for line in stream if line.strip())
    return texts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--max-similarity", type=float, default=0.75)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"Output already exists: {args.output}")
    rows = prepare(args.input, load_prior(), args.max_similarity)
    for row in rows:
        row["id"] = row["id"].replace("sw1-", "rc1-", 1)
        row["notes"] = "register-crossed contrast (formal threat vs casual benign); human review required"
    write(args.output, rows)
    print(json.dumps({"output": str(args.output), "pairs": len(rows) // 2,
                      "labels": dict(Counter(row["expectedAction"] for row in rows)),
                      "reviewStatus": "codex_provisional"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
