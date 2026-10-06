"""User-run stage-two-only comparison on a separate comment challenge set.

This diagnostic does not run the stage-one Moderation API and does not read
the project's final evaluation split.
"""

import argparse
import json
import math
import statistics
import time
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/restricted/gap_challenge_v1.jsonl"
BASE = ROOT / "results/kold-classifier/comment/best"
DKTC = ROOT / "results/kold-classifier/dktc-gap-v1/best"
OUTPUT = ROOT / "results/gap-challenge-v1/scores.jsonl"


def summarize(records, threshold):
    table = Counter()
    caught = []
    false_blocks = []
    for row in records:
        blocked = row["score"] >= threshold
        table[(row["caseType"], row["expectedAction"], blocked)] += 1
        if row["expectedAction"] == "BLOCK" and blocked:
            caught.append(row["id"])
        if row["expectedAction"] == "PASS" and blocked:
            false_blocks.append(row["id"])
    times = sorted(row["latencyMs"] for row in records)
    return {
        "threshold": threshold,
        "caught": len(caught),
        "blockTotal": sum(row["expectedAction"] == "BLOCK" for row in records),
        "falseBlocks": len(false_blocks),
        "passTotal": sum(row["expectedAction"] == "PASS" for row in records),
        "caughtIds": caught,
        "falseBlockIds": false_blocks,
        "byType": {f"{kind}/{label}/{('BLOCK' if blocked else 'PASS')}": count
                   for (kind, label, blocked), count in sorted(table.items())},
        "latencyP50Ms": statistics.median(times),
        "latencyP95Ms": times[math.ceil(0.95 * len(times)) - 1],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--base-model", type=Path, default=BASE)
    parser.add_argument("--dktc-model", type=Path, default=DKTC)
    parser.add_argument("--candidate-model", type=Path, default=None,
                        help="Optional third comment-only model scored alongside the other two")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--threshold", type=float, default=0.95)
    parser.add_argument("--threads", type=int, default=8)
    args = parser.parse_args()
    if not 0 <= args.threshold <= 1:
        parser.error("Threshold must be between 0 and 1")
    if args.output.exists():
        parser.error(f"Output already exists; choose another path: {args.output}")
    with args.data.open(encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream if line.strip()]
    if not rows or any(row.get("split") != "challenge_v1" for row in rows):
        raise ValueError("Expected challenge_v1 data")
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError("Duplicate challenge IDs")

    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    torch.set_num_threads(args.threads)
    all_records = []
    summaries = {}
    models = [("kold", args.base_model), ("dktc-gap-v1", args.dktc_model)]
    if args.candidate_model:
        models.append((args.candidate_model.parent.name, args.candidate_model))
    for name, model_dir in models:
        config = json.loads((model_dir / "stage2_config.json").read_text(encoding="utf-8"))
        if config.get("mode") != "comment":
            raise ValueError(f"Not a comment-only model: {model_dir}")
        tokenizer = AutoTokenizer.from_pretrained(model_dir)
        model = AutoModelForSequenceClassification.from_pretrained(model_dir)
        model.eval()

        def score(text):
            encoded = tokenizer(text, truncation=True, max_length=config["maxLength"],
                                return_tensors="pt")
            with torch.inference_mode():
                return torch.softmax(model(**encoded).logits, dim=-1)[0, 1].item()

        score(rows[0]["text"])
        records = []
        for row in rows:
            started = time.perf_counter()
            value = score(row["text"])
            records.append({
                "model": name,
                "id": row["id"],
                "caseType": row["caseType"],
                "expectedAction": row["expectedAction"],
                "score": round(value, 6),
                "latencyMs": round((time.perf_counter() - started) * 1000, 1),
            })
        all_records.extend(records)
        summaries[name] = summarize(records, args.threshold)
        del model, tokenizer

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as stream:
        for record in all_records:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(json.dumps({"data": str(args.data), "output": str(args.output),
                      "stageTwoOnly": True, "provisionalLabels": True,
                      "models": summaries}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
