"""Compare both classifiers on all comments in a selected evaluation split.

Uses saved stage-one results; makes no OpenAI API calls. The final split
requires an explicit flag and its own saved stage-one result file.
"""

import argparse
import json
from pathlib import Path

from src.eval_kold_classifier import BASELINE, DEV_DATA, read_jsonl


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "results/kold-classifier/comment/best"
DKTC = ROOT / "results/kold-classifier/dktc-gap-v1/best"
OUTPUT = ROOT / "results/full-dev/dktc-gap-v1-scores.jsonl"
FINAL_OUTPUT = ROOT / "results/final/dktc-gap-v1-scores.jsonl"


def load_development(split="dev", baseline_paths=BASELINE):
    rows = [row for path in DEV_DATA for row in read_jsonl(path)
            if row.get("split") == split]
    previous = [row for path in baseline_paths for row in read_jsonl(path)]
    by_id = {row["commentId"]: row for row in previous}
    expected_count = 109 if split == "dev" else 47
    if len(rows) != expected_count or len(by_id) != expected_count or {row["id"] for row in rows} != set(by_id):
        raise ValueError(f"{split} rows do not match saved stage-one results")
    if any(by_id[row["id"]]["modelStatus"] != "ok" for row in rows):
        raise ValueError("Saved stage-one results contain API failures")
    if any(by_id[row["id"]]["final"]["action"] not in {"PASS", "BLOCK"} for row in rows):
        raise ValueError("Saved stage-one results contain unknown actions")
    return rows, by_id


def metrics(records, action_key):
    block = [row for row in records if row["expectedAction"] == "BLOCK"]
    passed = [row for row in records if row["expectedAction"] == "PASS"]
    return {
        "caught": sum(row[action_key] == "BLOCK" for row in block),
        "blockTotal": len(block),
        "falseBlocks": sum(row[action_key] == "BLOCK" for row in passed),
        "passTotal": len(passed),
        "missedIds": [row["id"] for row in block if row[action_key] != "BLOCK"],
        "falseBlockIds": [row["id"] for row in passed if row[action_key] == "BLOCK"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-model", type=Path, default=BASE)
    parser.add_argument("--dktc-model", type=Path, default=DKTC)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--split", choices=("dev", "final"), default="dev")
    parser.add_argument("--allow-final", action="store_true")
    parser.add_argument("--stage-one-result", type=Path, action="append",
                        help="Saved first-stage JSONL; required for final split")
    parser.add_argument("--threshold", type=float, default=0.95)
    parser.add_argument("--threads", type=int, default=8)
    args = parser.parse_args()
    if not 0 <= args.threshold <= 1:
        parser.error("Threshold must be between 0 and 1")
    if args.split == "final" and not args.allow_final:
        parser.error("Final split requires --allow-final")
    if args.split == "final" and not args.stage_one_result:
        parser.error("Final split requires --stage-one-result from check_pipeline")
    if args.split == "dev" and args.stage_one_result:
        parser.error("Dev split uses the fixed saved stage-one baseline")
    if args.stage_one_result:
        missing = [path for path in args.stage_one_result if not path.is_file()]
        if missing:
            parser.error(f"Stage-one result file does not exist: {missing[0]}. Run check_pipeline first.")
    output = args.output or (FINAL_OUTPUT if args.split == "final" else OUTPUT)
    if output.exists():
        parser.error(f"Output already exists; choose a new output path: {output}")
    rows, baseline = load_development(
        args.split, args.stage_one_result if args.split == "final" else BASELINE
    )

    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    torch.set_num_threads(args.threads)
    all_records = []
    summaries = {}
    for name, model_dir in (("kold", args.base_model), ("dktc-gap-v1", args.dktc_model)):
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
            value = score(row["text"])
            first = baseline[row["id"]]["final"]["action"]
            second = "BLOCK" if value >= args.threshold else "PASS"
            records.append({
                "model": name,
                "id": row["id"],
                "expectedAction": row["expectedAction"],
                "caseType": row.get("caseType"),
                "stageOneAction": first,
                "modelAloneAction": second,
                "pipelineAction": "BLOCK" if first == "BLOCK" or second == "BLOCK" else "PASS",
                "score": round(value, 6),
            })
        all_records.extend(records)
        summaries[name] = {
            "modelAlone": metrics(records, "modelAloneAction"),
            "stageOnePlusModel": metrics(records, "pipelineAction"),
            "byCaseType": {kind: metrics([row for row in records if row["caseType"] == kind],
                                         "pipelineAction")
                           for kind in sorted({row["caseType"] for row in records
                                               if row["caseType"]})},
        }
        del model, tokenizer

    first_stage = [{**row, "stageOneAction": baseline[row["id"]]["final"]["action"]}
                   for row in rows]
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as stream:
        for record in all_records:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(json.dumps({
        "data": f"{len(rows)} {args.split} comments",
        "threshold": args.threshold,
        "stageOneOnly": metrics(first_stage, "stageOneAction"),
        "models": summaries,
        "output": str(output),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
