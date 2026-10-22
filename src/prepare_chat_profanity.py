"""Sample and clean the Kaggle Korean hate-chat TSV for exploratory training.

Source: kaggle.com/datasets/tanat05/korean-hate-chat-data (CC BY-NC-SA 4.0):
local, non-commercial experiments only. Labels are coarse profanity labels, not
the service BLOCK policy. The raw file stays outside Git. Rows matching any
evaluation text are dropped, and a small audit sheet is written so a person can
estimate label noise before training.
"""

import argparse
import csv
import hashlib
import json
import random
import re
from collections import Counter
from pathlib import Path

from src.train_dktc_gap_classifier import PROTECTED_EVAL, protected_texts
from src.validate_dktc_review_sheet import normalized


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data/data.tsv"
OUTPUT_DIR = ROOT / "data/restricted/chat_profanity"
SOURCE = "kaggle tanat05/korean-hate-chat-data (CC BY-NC-SA 4.0)"

URL = re.compile(r"https?://|www\.|discord|\.com|\.kr|\.net|cdn\.", re.I)
ID_LIKE = re.compile(r"\d{6,}|[A-Za-z0-9_]{8,}")
LONG_RUN = re.compile(r"(.)\1{7,}")
HANGUL = re.compile(r"[가-힣]")
WORDISH = re.compile(r"[가-힣A-Za-z0-9\s]")


def usable(text):
    """Drop links, IDs, bot commands, near-empty or mostly non-Korean rows."""
    if not 2 <= len(text) <= 150 or text.startswith(("!", "/", "$")):
        return False
    if URL.search(text) or ID_LIKE.search(text) or LONG_RUN.search(text) or "@" in text:
        return False
    compact = text.replace(" ", "")
    if len(HANGUL.findall(compact)) < 0.5 * len(compact):
        return False
    return len(WORDISH.findall(text)) >= 0.7 * len(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=INPUT)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--per-class", type=int, default=100000)
    parser.add_argument("--validation-percent", type=int, default=2)
    parser.add_argument("--audit-per-class", type=int, default=50)
    parser.add_argument("--seed", type=int, default=17)
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error(f"Output already exists; choose a new directory: {args.output_dir}")
    if args.per_class < 1 or not 0 < args.validation_percent < 50:
        parser.error("Invalid sample size or validation percent")

    blocked = protected_texts(PROTECTED_EVAL)
    rng = random.Random(args.seed)
    capacity = int(args.per_class * 1.3) + args.audit_per_class  # slack for dedupe
    reservoir = {"0": [], "1": []}
    seen = Counter()
    stats = Counter()
    csv.field_size_limit(10**7)
    with args.input.open(encoding="utf-8", newline="") as stream:
        reader = csv.reader(stream, delimiter="\t")
        next(reader)
        for row in reader:
            stats["rows"] += 1
            if len(row) != 2 or row[1] not in reservoir:
                stats["badRow"] += 1
                continue
            text = normalized(row[0])
            if not usable(text):
                stats["filtered"] += 1
                continue
            if text in blocked:
                stats["evalOverlap"] += 1
                continue
            label = row[1]
            seen[label] += 1
            bucket = reservoir[label]
            if len(bucket) < capacity:
                bucket.append(text)
            else:
                slot = rng.randrange(seen[label])
                if slot < capacity:
                    bucket[slot] = text

    train, validation, audit = [], [], []
    used = set()
    for label, bucket in reservoir.items():
        rng.shuffle(bucket)
        picked = []
        for text in bucket:
            if text in used:
                continue
            used.add(text)
            picked.append(text)
            if len(picked) == args.per_class + args.audit_per_class:
                break
        for text in picked[:args.audit_per_class]:
            audit.append((label, text))
        for text in picked[args.audit_per_class:]:
            digest = int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16)
            record = {"id": f"chat-{digest % 10**12:012d}", "text": text,
                      "label": int(label), "source": SOURCE}
            (validation if digest % 100 < args.validation_percent else train).append(record)
    if not train or not validation:
        raise ValueError("Sampling produced an empty split")
    rng.shuffle(train)

    args.output_dir.mkdir(parents=True)
    for name, rows in (("train", train), ("validation", validation)):
        with (args.output_dir / f"{name}.jsonl").open("w", encoding="utf-8", newline="\n") as out:
            for record in rows:
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
    rng.shuffle(audit)
    with (args.output_dir / "audit_sheet.csv").open("w", encoding="utf-8-sig", newline="") as out:
        writer = csv.writer(out)
        writer.writerow(["id", "원래 라벨(1=욕설/공격)", "text", "라벨 틀림? (틀리면 X)", "메모"])
        for index, (label, text) in enumerate(audit, 1):
            writer.writerow([f"audit-{index:03d}", label, text, "", ""])
    manifest = {
        "source": SOURCE, "seed": args.seed, "perClass": args.per_class,
        "rowsScanned": stats["rows"], "filtered": stats["filtered"],
        "evalOverlapDropped": stats["evalOverlap"], "eligible": dict(seen),
        "train": {"rows": len(train), "label1": sum(r["label"] for r in train)},
        "validation": {"rows": len(validation), "label1": sum(r["label"] for r in validation)},
        "auditRows": len(audit),
        "warning": "coarse profanity labels; exploratory, non-commercial only; audit label noise before use",
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
