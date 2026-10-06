"""Build Codex-provisional, comment-level threat/benign pairs for stage two.

Rows come from data/restricted/threat_context_v1.tsv. Pairs never cross the
train/heldout split, and any text seen in dev, final, or the earlier challenge
and DKTC sets is rejected. Labels are not human approved.
"""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from src.validate_dktc_review_sheet import normalized


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/restricted/threat_context_v1.tsv"
TRAIN = ROOT / "data/restricted/threat_context_v1_train.jsonl"
HELDOUT = ROOT / "data/restricted/threat_context_v1_heldout.jsonl"
COLUMNS = {"pairId", "split", "subtype", "expectedAction", "text"}


def known_texts():
    texts = set()
    paths = [ROOT / "data/context_eval.jsonl", ROOT / "data/realistic_comments.jsonl",
             ROOT / "data/restricted/gap_challenge_v1.jsonl",
             ROOT / "data/restricted/dktc/provisional_comments.jsonl"]
    for path in paths:
        if path.exists():
            with path.open(encoding="utf-8") as stream:
                texts.update(normalized(json.loads(line)["text"]) for line in stream if line.strip())
    return texts


def write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=SOURCE)
    parser.add_argument("--train-output", type=Path, default=TRAIN)
    parser.add_argument("--heldout-output", type=Path, default=HELDOUT)
    args = parser.parse_args()
    for path in (args.train_output, args.heldout_output):
        if path.exists():
            parser.error(f"Output already exists; choose another path: {path}")
    with args.input.open(encoding="utf-8-sig", newline="") as stream:
        source = list(csv.DictReader(stream, delimiter="\t"))
    if not source or any(set(row) != COLUMNS for row in source):
        raise ValueError("Threat context TSV columns changed")
    excluded = known_texts()
    seen = set()
    pair_split = {}
    pair_labels = {}
    train, heldout = [], []
    for index, row in enumerate(source, 1):
        text = normalized(row["text"])
        action = row["expectedAction"]
        if action not in {"BLOCK", "PASS"} or row["split"] not in {"train", "heldout"} or not text:
            raise ValueError(f"Invalid row {index}")
        if text in seen or text in excluded:
            raise ValueError(f"Duplicate or previously used text: {row['pairId']} {text}")
        if pair_split.setdefault(row["pairId"], row["split"]) != row["split"]:
            raise ValueError(f"Pair crosses split: {row['pairId']}")
        pair_labels.setdefault(row["pairId"], Counter())[action] += 1
        seen.add(text)
        record = {
            "id": f"tc1-{row['pairId']}-{action.lower()}",
            "source": "synthetic (Codex-written)",
            "text": text,
            "gapType": row["subtype"],
            "caseType": "threat",
            "pairId": row["pairId"],
            "expectedAction": action,
            "reviewStatus": "codex_provisional",
            "notes": "paired threat/benign contrast; not human approved",
        }
        if row["split"] == "heldout":
            heldout.append(record | {"split": "challenge_v1"})
        else:
            train.append(record)
    if any(counts != Counter({"BLOCK": 1, "PASS": 1}) for counts in pair_labels.values()):
        raise ValueError("Every pair needs exactly one BLOCK and one PASS")
    write(args.train_output, train)
    write(args.heldout_output, heldout)
    print(json.dumps({
        "train": dict(Counter(row["expectedAction"] for row in train)),
        "heldout": dict(Counter(row["expectedAction"] for row in heldout)),
        "trainOutput": str(args.train_output), "heldoutOutput": str(args.heldout_output),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
