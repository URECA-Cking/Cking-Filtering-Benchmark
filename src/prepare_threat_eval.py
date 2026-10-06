"""Freeze a new, unpaired comment evaluation set (threat_eval_v2).

Rejects exact or near-duplicate texts against every training, dev, final,
challenge, and held-out set, then writes the JSONL and a SHA-256 manifest so
later edits are detectable. Labels are Codex-provisional, not human approved.
Never use this set for training, threshold tuning, or model selection.
"""

import argparse
import csv
import difflib
import hashlib
import json
from collections import Counter
from pathlib import Path

from src.prepare_threat_context import ROOT, known_texts, write
from src.validate_dktc_review_sheet import normalized


SOURCE = ROOT / "data/restricted/threat_eval_v2.tsv"
OUTPUT = ROOT / "data/restricted/threat_eval_v2.jsonl"
MANIFEST = ROOT / "data/restricted/threat_eval_v2.sha256"
EARLIER = [ROOT / "data/restricted/threat_context_v1_train.jsonl",
           ROOT / "data/restricted/threat_context_v1_heldout.jsonl",
           ROOT / "data/restricted/stalking_warning_v1_train.jsonl",
           ROOT / "data/restricted/threat_eval_v2.jsonl"]
COLUMNS = {"id", "caseType", "expectedAction", "text"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--max-similarity", type=float, default=0.75)
    args = parser.parse_args()
    for path in (args.output, args.manifest):
        if path.exists():
            parser.error(f"Already frozen; choose another path: {path}")
    with args.input.open(encoding="utf-8-sig", newline="") as stream:
        source = list(csv.DictReader(stream, delimiter="\t"))
    if not source or any(set(row) != COLUMNS for row in source):
        raise ValueError("Eval TSV columns changed")
    earlier = known_texts()
    for path in EARLIER:
        if path.resolve() == args.output.resolve():
            continue  # the set being created now is not an earlier set
        with path.open(encoding="utf-8") as stream:
            earlier.update(normalized(json.loads(line)["text"]) for line in stream if line.strip())
    rows, seen, ids = [], set(), set()
    for row in source:
        text = normalized(row["text"])
        if row["expectedAction"] not in {"BLOCK", "PASS"} or not text or row["id"] in ids:
            raise ValueError(f"Invalid or duplicate row: {row['id']}")
        if text in seen or text in earlier:
            raise ValueError(f"Duplicate of an earlier text: {row['id']}")
        nearest = max(earlier, key=lambda old: difflib.SequenceMatcher(None, text, old).ratio())
        similarity = difflib.SequenceMatcher(None, text, nearest).ratio()
        if similarity > args.max_similarity:
            raise ValueError(f"Too similar ({similarity:.2f}) to earlier text: {row['id']}")
        ids.add(row["id"])
        seen.add(text)
        rows.append({
            "id": row["id"], "source": "synthetic (Codex-written, unpaired)", "text": text,
            "caseType": row["caseType"], "expectedAction": row["expectedAction"],
            "reviewStatus": "codex_provisional", "split": "challenge_v1",
            "notes": "frozen evaluation only; not human approved",
        })
    write(args.output, rows)
    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
    args.manifest.write_text(f"{digest}  {args.output.name}\n", encoding="utf-8")
    print(json.dumps({"counts": dict(Counter(row["expectedAction"] for row in rows)),
                      "byType": dict(Counter(row["caseType"] for row in rows)),
                      "sha256": digest, "output": str(args.output)},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
