"""Create a human review CSV from local DKTC triage and contrast examples."""

import argparse
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "data/restricted/dktc"
FIELDS = (
    "id", "source", "conversationId", "text", "gapType",
    "suggestedDisposition", "suggestionReason", "reviewStatus",
    "expectedAction", "notes",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dktc", type=Path, default=LOCAL / "gap_review_batch.jsonl")
    parser.add_argument("--contrast", type=Path, default=LOCAL / "contrast_pass_candidates.tsv")
    parser.add_argument("--output", type=Path, default=LOCAL / "gap_review_sheet.csv")
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"Output already exists; preserve human edits: {args.output}")

    with args.dktc.open(encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream if line.strip()]
    if any(row["reviewStatus"] != "pending_human" or row["expectedAction"] is not None
           for row in rows):
        raise ValueError("DKTC review candidates must be unlabeled")

    with args.contrast.open(encoding="utf-8-sig", newline="") as stream:
        contrast = list(csv.DictReader(stream, delimiter="\t"))
    for row in contrast:
        if set(row) != {"id", "text", "gapType", "reason"} or not all(row.values()):
            raise ValueError("Invalid synthetic contrast row")
        rows.append({
            "id": row["id"],
            "source": "synthetic (newly authored for local review)",
            "conversationId": "",
            "text": row["text"],
            "gapType": row["gapType"],
            "suggestedDisposition": "propose_pass",
            "suggestionReason": row["reason"],
            "reviewStatus": "pending_human",
            "expectedAction": None,
            "notes": "",
        })
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError("Duplicate IDs in review sheet")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) or "" for field in FIELDS})
    print(f"Review sheet: {len(rows)} rows ({len(contrast)} synthetic PASS proposals) -> {args.output}")


if __name__ == "__main__":
    main()
