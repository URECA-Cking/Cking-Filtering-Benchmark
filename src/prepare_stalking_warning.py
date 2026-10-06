"""Validate and export provisional stalking/warning training pairs.

The unpaired review TSV is deliberately excluded. The frozen threat_eval_v2
set is read only for leakage checks and must never enter training.
"""

import argparse
import csv
import difflib
import json
from collections import Counter
from pathlib import Path

from src.prepare_threat_context import ROOT, write
from src.validate_dktc_review_sheet import normalized


SOURCE = ROOT / "data/restricted/stalking_warning_v1.tsv"
OUTPUT = ROOT / "data/restricted/stalking_warning_v1_train.jsonl"
PRIOR = [
    ROOT / "data/context_eval.jsonl",
    ROOT / "data/realistic_comments.jsonl",
    ROOT / "data/restricted/gap_challenge_v1.jsonl",
    ROOT / "data/restricted/dktc/provisional_comments.jsonl",
    ROOT / "data/restricted/threat_context_v1_train.jsonl",
    ROOT / "data/restricted/threat_context_v1_heldout.jsonl",
    ROOT / "data/restricted/threat_eval_v2.jsonl",
]
COLUMNS = {"pairId", "subtype", "expectedAction", "text"}


def load_prior():
    texts = []
    for path in PRIOR:
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as stream:
            texts.extend(normalized(json.loads(line)["text"]) for line in stream if line.strip())
    return texts


def prepare(source, prior, max_similarity):
    with source.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if set(reader.fieldnames or ()) != COLUMNS:
            raise ValueError("Unexpected TSV columns")
        entries = list(reader)
    if not entries:
        raise ValueError("No candidate rows")
    rows, pair_labels, seen = [], {}, set()
    for line_number, row in enumerate(entries, 2):
        pair_id = row["pairId"].strip()
        text = normalized(row["text"])
        action = row["expectedAction"].strip()
        if not pair_id or not row["subtype"].strip() or action not in {"BLOCK", "PASS"} or not text:
            raise ValueError(f"Invalid candidate at line {line_number}")
        if text in seen:
            raise ValueError(f"Duplicate candidate at line {line_number}")
        nearest = max((difflib.SequenceMatcher(None, text, old).ratio() for old in prior), default=0)
        if nearest >= max_similarity:
            raise ValueError(f"Prior-set overlap at line {line_number}: {nearest:.2f} ({text})")
        seen.add(text)
        pair_labels.setdefault(pair_id, Counter())[action] += 1
        rows.append({
            "id": f"sw1-{pair_id}-{action.lower()}",
            "source": "synthetic (Codex-written)",
            "text": text,
            "caseType": "threat",
            "gapType": row["subtype"],
            "pairId": pair_id,
            "expectedAction": action,
            "reviewStatus": "codex_provisional",
            "notes": "Provisional comment-level contrast; human review required before training use",
        })
    if any(counts != Counter({"BLOCK": 1, "PASS": 1}) for counts in pair_labels.values()):
        raise ValueError("Every pair must contain one BLOCK and one PASS")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--max-similarity", type=float, default=0.85)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"Output already exists: {args.output}")
    if not 0 < args.max_similarity <= 1:
        parser.error("--max-similarity must be in (0, 1]")
    rows = prepare(args.input, load_prior(), args.max_similarity)
    write(args.output, rows)
    print(json.dumps({"output": str(args.output), "pairs": len(rows) // 2,
                      "labels": dict(Counter(row["expectedAction"] for row in rows)),
                      "reviewStatus": "codex_provisional"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
