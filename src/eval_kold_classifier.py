"""Evaluate a trained KOLD classifier only on stage-one PASS development comments.

The project's final split is deliberately never read. First-stage BLOCK rows
never reach this classifier, matching the intended production pipeline.
"""

import argparse
import json
import math
import statistics
import time
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEV_DATA = (ROOT / "data/context_eval.jsonl", ROOT / "data/realistic_comments.jsonl")
BASELINE = (
    ROOT / "results/pipeline-20261001T141252Z.jsonl",
    ROOT / "results/pipeline-20261001T145042Z.jsonl",
)


def read_jsonl(path):
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def eligible_rows():
    dev = [row for path in DEV_DATA for row in read_jsonl(path) if row.get("split") == "dev"]
    baseline = {row["commentId"]: row for path in BASELINE for row in read_jsonl(path)}
    if len(dev) != 109 or {row["id"] for row in dev} != set(baseline):
        raise ValueError("Development data and saved first-stage results do not match")
    if any(baseline[row["id"]]["modelStatus"] != "ok" for row in dev):
        raise ValueError("First-stage results include API failures")
    return [row for row in dev if baseline[row["id"]]["final"]["action"] == "PASS"]


def counts_at_threshold(records, threshold):
    positives = [row for row in records if row["expected"] == "BLOCK"]
    negatives = [row for row in records if row["expected"] == "PASS"]
    caught = [row for row in positives if row["score"] >= threshold]
    false_blocks = [row for row in negatives if row["score"] >= threshold]
    return {
        "threshold": threshold,
        "additionalBlocks": len(caught),
        "missedBlocks": len(positives) - len(caught),
        "newFalseBlocks": len(false_blocks),
        "blockDenominator": len(positives),
        "passDenominator": len(negatives),
        "caughtIds": [row["id"] for row in caught],
        "falseBlockIds": [row["id"] for row in false_blocks],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path,
                        default=ROOT / "results/kold-classifier/comment/best")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--threads", type=int, default=8)
    args = parser.parse_args()
    if not 0 <= args.threshold <= 1:
        parser.error("--threshold must be between 0 and 1")

    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    config = json.loads((args.model_dir / "stage2_config.json").read_text(encoding="utf-8"))
    if config["mode"] != "comment":
        raise ValueError("This evaluation accepts comment-only models")
    torch.set_num_threads(args.threads)
    tokenizer = AutoTokenizer.from_pretrained(args.model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(args.model_dir)
    model.eval()
    rows = eligible_rows()

    def score_row(row):
        encoded = tokenizer(
            row["text"],
            truncation=True,
            max_length=config["maxLength"],
            return_tensors="pt",
        )
        with torch.inference_mode():
            logits = model(**encoded).logits
            score = torch.softmax(logits, dim=-1)[0, 1].item()
        return score

    # Separate one-time model startup from per-comment latency.
    score_row(rows[0])
    records = []
    for index, row in enumerate(rows, 1):
        started = time.perf_counter()
        score = score_row(row)
        record = {
            "id": row["id"],
            "expected": row["expectedAction"],
            "caseType": row.get("caseType"),
            "score": round(score, 6),
            "latencyMs": round((time.perf_counter() - started) * 1000, 1),
        }
        records.append(record)
        print(f"{index}/{len(rows)} {record['id']} expected={record['expected']} "
              f"score={record['score']:.4f} {record['latencyMs']:.1f}ms", flush=True)

    output = args.output or args.model_dir.parent / "stage2-dev-scores.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")

    times = sorted(record["latencyMs"] for record in records)
    print("stage-one PASS only", len(rows), "positive", sum(r["expected"] == "BLOCK" for r in records),
          "normal", sum(r["expected"] == "PASS" for r in records))
    print("latency p50", statistics.median(times), "p95", times[math.ceil(0.95 * len(times)) - 1], "ms")
    for threshold in sorted({0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, args.threshold}):
        result = counts_at_threshold(records, threshold)
        print(f"threshold {threshold:.2f}: additional blocks "
              f"{result['additionalBlocks']}/{result['blockDenominator']}, "
              f"new false blocks {result['newFalseBlocks']}/{result['passDenominator']}")
    chosen = counts_at_threshold(records, args.threshold)
    print("at selected threshold", json.dumps(chosen, ensure_ascii=False))
    by_type = Counter((row["caseType"], row["expected"], row["score"] >= args.threshold)
                      for row in records if row["caseType"])
    for (case_type, expected, blocked), count in sorted(by_type.items()):
        print(case_type, expected, "BLOCK" if blocked else "PASS", count)
    print("scores saved", output)


if __name__ == "__main__":
    main()
