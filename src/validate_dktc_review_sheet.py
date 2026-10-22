"""Validate human-reviewed DKTC CSV and export approved local comments."""

import argparse
import csv
import json
import unicodedata
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SHEET = ROOT / "data/restricted/dktc/gap_review_sheet.csv"
DEFAULT_OUTPUT = ROOT / "data/restricted/dktc/approved_comments.jsonl"


def normalized(text):
    return " ".join(unicodedata.normalize("NFC", text).split())


def dev_texts():
    texts = set()
    for name in ("context_eval.jsonl", "realistic_comments.jsonl"):
        with (ROOT / "data" / name).open(encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                if row.get("split") == "dev":
                    texts.add(normalized(row["text"]))
    return texts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sheet", type=Path, default=DEFAULT_SHEET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.sheet.resolve() == args.output.resolve():
        parser.error("Sheet and output must differ")

    with args.sheet.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    required = {"id", "source", "conversationId", "text", "gapType",
                "suggestedDisposition", "suggestionReason", "reviewStatus",
                "expectedAction", "notes"}
    if not rows or any(set(row) != required for row in rows):
        raise ValueError("Review sheet columns are missing or changed")
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError("Duplicate review IDs")

    approved = []
    excluded = Counter()
    seen_texts = set()
    dev = dev_texts()
    for row in rows:
        status = row["reviewStatus"].strip()
        action = row["expectedAction"].strip().upper()
        if status == "pending_human" and not action:
            excluded["pending_human"] += 1
            continue
        if status != "approved" or action not in {"BLOCK", "PASS"}:
            raise ValueError(f"Invalid status/action for {row['id']}")
        if row["suggestedDisposition"] == "exclude":
            raise ValueError(f"Search-error example cannot be approved for training: {row['id']}")
        if not row["notes"].strip():
            raise ValueError(f"Approved row needs review rationale in notes: {row['id']}")
        text = normalized(row["text"])
        if not text:
            raise ValueError(f"Empty approved text: {row['id']}")
        if text in dev:
            raise ValueError(f"Approved text duplicates development evaluation: {row['id']}")
        if text in seen_texts:
            raise ValueError(f"Duplicate approved text: {row['id']}")
        seen_texts.add(text)
        approved.append({
            "id": row["id"],
            "source": row["source"],
            "conversationId": row["conversationId"] or None,
            "text": text,
            "gapType": row["gapType"],
            "expectedAction": action,
            "reviewStatus": "approved",
            "notes": row["notes"].strip(),
        })

    counts = Counter(row["expectedAction"] for row in approved)
    if counts["BLOCK"] == 0 or counts["PASS"] == 0:
        parser.error(
            f"CSV has approved BLOCK={counts['BLOCK']}, PASS={counts['PASS']} "
            f"(pending={excluded['pending_human']}). Open {args.sheet}, then for each "
            "confirmed row set reviewStatus=approved, expectedAction=BLOCK or PASS, "
            "and write a reason in notes. Save the CSV before rerunning."
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as stream:
        for row in approved:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"approved": dict(counts), "pending": excluded["pending_human"],
                      "output": str(args.output)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
