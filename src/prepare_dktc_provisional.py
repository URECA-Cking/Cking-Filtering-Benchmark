"""Export Codex-reviewed exploratory labels without claiming human approval."""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from src.validate_dktc_review_sheet import dev_texts, normalized


ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "data/restricted/dktc"
BLOCK_IDS = {
    "dktc-train-12-6", "dktc-train-1125-10", "dktc-train-1560-6",
    "dktc-train-1837-1", "dktc-train-2024-9", "dktc-train-2198-7",
    "dktc-train-2334-9", "dktc-train-2782-7", "dktc-train-2885-9",
    "dktc-train-3166-7", "dktc-train-3715-6", "dktc-train-483-6",
    "dktc-train-2336-5",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sheet", type=Path, default=LOCAL / "gap_review_sheet.csv")
    parser.add_argument("--output", type=Path, default=LOCAL / "provisional_comments.jsonl")
    args = parser.parse_args()
    if args.sheet.resolve() == args.output.resolve():
        parser.error("Sheet and output paths must differ")
    with args.sheet.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    by_id = {row["id"]: row for row in rows}
    if len(by_id) != len(rows) or BLOCK_IDS - by_id.keys():
        raise ValueError("Review sheet IDs changed or are duplicated")
    selected = []
    used_text = set()
    held_out = dev_texts()
    for row in rows:
        if row["id"] in BLOCK_IDS:
            if row["suggestedDisposition"] != "propose_block":
                raise ValueError(f"Changed BLOCK suggestion: {row['id']}")
            action = "BLOCK"
        elif row["source"].startswith("synthetic (") and row["suggestedDisposition"] == "propose_pass":
            action = "PASS"
        else:
            continue
        text = normalized(row["text"])
        if not text or text in used_text or text in held_out:
            raise ValueError(f"Duplicate, empty, or development text: {row['id']}")
        used_text.add(text)
        selected.append({
            "id": row["id"],
            "source": row["source"],
            "conversationId": row["conversationId"] or None,
            "text": text,
            "gapType": row["gapType"],
            "expectedAction": action,
            "reviewStatus": "codex_provisional",
            "notes": row["suggestionReason"],
        })
    counts = Counter(row["expectedAction"] for row in selected)
    if counts["BLOCK"] != len(BLOCK_IDS) or counts["PASS"] != 12:
        raise ValueError(f"Unexpected provisional counts: {counts}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as stream:
        for row in selected:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"codexProvisional": dict(counts), "output": str(args.output)},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
