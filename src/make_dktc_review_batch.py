"""Join local DKTC candidate IDs with provisional, non-training review notes."""

import argparse
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "data/restricted/dktc"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, default=LOCAL / "threat_candidates.jsonl")
    parser.add_argument("--decisions", type=Path, default=LOCAL / "gap_review_decisions.tsv")
    parser.add_argument("--output", type=Path, default=LOCAL / "gap_review_batch.jsonl")
    args = parser.parse_args()
    if len({path.resolve() for path in (args.candidates, args.decisions, args.output)}) != 3:
        parser.error("Candidates, decisions, and output must be distinct files")

    with args.candidates.open(encoding="utf-8") as stream:
        candidates = [json.loads(line) for line in stream if line.strip()]
    by_id = {row["id"]: row for row in candidates}
    if len(by_id) != len(candidates):
        raise ValueError("Duplicate candidate IDs")

    with args.decisions.open(encoding="utf-8-sig", newline="") as stream:
        decisions = list(csv.DictReader(stream, delimiter="\t"))
    expected_fields = {"id", "gapType", "suggestedDisposition", "reason"}
    if not decisions or any(set(row) != expected_fields for row in decisions):
        raise ValueError("Expected nonempty id, gapType, suggestedDisposition, reason TSV")
    if len({row["id"] for row in decisions}) != len(decisions):
        raise ValueError("Duplicate review IDs")

    output = []
    for decision in decisions:
        if decision["id"] not in by_id:
            raise ValueError(f"Unknown candidate ID: {decision['id']}")
        if decision["suggestedDisposition"] not in {"propose_block", "needs_context", "exclude"}:
            raise ValueError(f"Unknown suggestion for {decision['id']}")
        if not decision["gapType"] or not decision["reason"]:
            raise ValueError(f"Missing review rationale for {decision['id']}")
        candidate = by_id[decision["id"]].copy()
        if candidate["reviewStatus"] != "pending_human" or candidate["expectedAction"] is not None:
            raise ValueError("Candidates must remain unlabeled before human review")
        candidate.update({
            "gapType": decision["gapType"],
            "suggestedDisposition": decision["suggestedDisposition"],
            "suggestionReason": decision["reason"],
        })
        output.append(candidate)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as stream:
        for row in output:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({
        "reviewRows": len(output),
        "suggestions": {name: sum(row["suggestedDisposition"] == name for row in output)
                        for name in ("propose_block", "needs_context", "exclude")},
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
