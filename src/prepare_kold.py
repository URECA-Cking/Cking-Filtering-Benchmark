"""Prepare the public KOLD corpus for local, non-commercial classifier experiments.

KOLD's OFF label means offensiveness, not this project's final BLOCK policy.
Processed comments stay under data/restricted/ and are not committed to Git.
"""

import argparse
import json
import random
import re
import unicodedata
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data/raw/kold/data/kold_v1.json"
DEFAULT_OUTPUT = ROOT / "data/restricted/kold"
WHITESPACE = re.compile(r"\s+")


def normalize_text(value):
    if not isinstance(value, str):
        raise ValueError("Expected a text field")
    return WHITESPACE.sub(" ", unicodedata.normalize("NFC", value)).strip()


def prepare_rows(raw):
    counts = Counter(normalize_text(row["comment"]) for row in raw)
    prepared = []
    dropped_duplicate = 0
    dropped_invalid = 0
    for row in raw:
        comment = normalize_text(row["comment"])
        title = normalize_text(row["title"])
        if not comment or len(comment) > 500 or not title or not isinstance(row["OFF"], bool):
            dropped_invalid += 1
            continue
        # Remove every occurrence of a repeated comment. A repeated text can
        # have a different label or title and could leak across data splits.
        if counts[comment] > 1:
            dropped_duplicate += 1
            continue
        prepared.append({
            "id": row["guid"],
            "text": comment,
            "postText": title,
            "offensive": row["OFF"],
            "source": row["source"],
            "targetType": row["TGT"],  # For analysis only; never use as model input.
        })
    if len({row["id"] for row in prepared}) != len(prepared):
        raise ValueError("Duplicate KOLD IDs")
    return prepared, dropped_duplicate, dropped_invalid


def split_by_post(rows, seed):
    groups = {}
    for row in rows:
        groups.setdefault((row["source"], row["postText"]), []).append(row)
    keys = sorted(groups)
    random.Random(seed).shuffle(keys)

    targets = (round(len(rows) * 0.8), round(len(rows) * 0.9))
    result = {"train": [], "validation": [], "test": []}
    for key in keys:
        count = len(result["train"]) + len(result["validation"])
        split = "train" if len(result["train"]) < targets[0] else (
            "validation" if count < targets[1] else "test"
        )
        result[split].extend(groups[key])
    return result


def write_jsonl(path, rows):
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            # The title is needed to split by post, but the classifier uses
            # only comment text. Do not retain post text in training files.
            output = {key: value for key, value in row.items() if key != "postText"}
            stream.write(json.dumps(output, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seed", type=int, default=17)
    args = parser.parse_args()

    raw = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("KOLD input must be a JSON array")
    rows, dropped_duplicate, dropped_invalid = prepare_rows(raw)
    splits = split_by_post(rows, args.seed)

    # Check both post and comment separation before writing any files.
    for field in ("id", "text"):
        values = [row[field] for part in splits.values() for row in part]
        if len(values) != len(set(values)):
            raise ValueError(f"Repeated {field} across processed data")
    post_sets = [
        {(row["source"], row["postText"]) for row in part}
        for part in splits.values()
    ]
    if any(post_sets[i] & post_sets[j] for i in range(3) for j in range(i + 1, 3)):
        raise ValueError("Post group leaked across splits")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "source": "https://github.com/boychaboy/KOLD",
        "rawRows": len(raw),
        "droppedDuplicateRows": dropped_duplicate,
        "droppedInvalidRows": dropped_invalid,
        "seed": args.seed,
        "labelMeaning": "KOLD OFF (offensiveness); not project PASS/BLOCK",
        "splits": {},
    }
    for name, part in splits.items():
        write_jsonl(args.output_dir / f"{name}.jsonl", part)
        summary["splits"][name] = {
            "rows": len(part),
            "offensive": sum(row["offensive"] for row in part),
            "normal": sum(not row["offensive"] for row in part),
            "postGroups": len({(row["source"], row["postText"]) for row in part}),
        }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
