"""Build a separate, Codex-provisional comment-only challenge set."""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from src.validate_dktc_review_sheet import dev_texts, normalized


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TSV = ROOT / "data/restricted/gap_challenge_v1.tsv"
DEFAULT_OUTPUT = ROOT / "data/restricted/gap_challenge_v1.jsonl"
TRAINING = ROOT / "data/restricted/dktc/provisional_comments.jsonl"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_TSV)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error("Input and output must differ")
    with args.input.open(encoding="utf-8-sig", newline="") as stream:
        source = list(csv.DictReader(stream, delimiter="\t"))
    if len(source) != 48:
        raise ValueError(f"Expected 48 challenge rows, found {len(source)}")
    train_texts = set()
    if TRAINING.exists():
        with TRAINING.open(encoding="utf-8") as stream:
            train_texts = {normalized(json.loads(line)["text"]) for line in stream if line.strip()}
    excluded = dev_texts() | train_texts
    ids = set()
    texts = set()
    rows = []
    for row in source:
        if set(row) != {"id", "caseType", "expectedAction", "text", "notes"}:
            raise ValueError("Challenge TSV columns changed")
        if row["caseType"] not in {"threat", "quote", "sarcasm"}:
            raise ValueError(f"Invalid case type: {row['id']}")
        if row["expectedAction"] not in {"BLOCK", "PASS"} or not row["notes"].strip():
            raise ValueError(f"Invalid label or rationale: {row['id']}")
        value = normalized(row["text"])
        if not value or row["id"] in ids or value in texts or value in excluded:
            raise ValueError(f"Duplicate, empty, or prior evaluation/training text: {row['id']}")
        ids.add(row["id"])
        texts.add(value)
        rows.append({
            "id": row["id"],
            "text": value,
            "expectedAction": row["expectedAction"],
            "caseType": row["caseType"],
            "source": "synthetic",
            "reviewStatus": "codex_provisional",
            "split": "challenge_v1",
            "notes": row["notes"],
        })
    counts = Counter((row["caseType"], row["expectedAction"]) for row in rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"rows": len(rows), "byType": {f"{kind}/{label}": count
                                                   for (kind, label), count in sorted(counts.items())},
                      "output": str(args.output)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
