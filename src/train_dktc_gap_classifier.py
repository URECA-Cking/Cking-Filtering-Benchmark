"""Adapt the existing KOLD checkpoint using local DKTC gap examples.

By default, labels are Codex-provisional and the model is exploratory only.
Training and model evaluation are intentionally user-run steps.
"""

import argparse
import json
import random
from collections import Counter
from pathlib import Path

from src.train_kold_classifier import metrics, select_rows
from src.validate_dktc_review_sheet import dev_texts, normalized


ROOT = Path(__file__).resolve().parents[1]
APPROVED = ROOT / "data/restricted/dktc/provisional_comments.jsonl"
KOLD = ROOT / "data/restricted/kold"
EVAL_SPLITS = {"dev", "final", "challenge_v1"}
PROTECTED_EVAL = [
    ROOT / "data/restricted/gap_challenge_v1.jsonl",
    ROOT / "data/restricted/threat_context_v1_heldout.jsonl",
    ROOT / "data/restricted/threat_eval_v2.jsonl",
]
BASE = ROOT / "results/kold-classifier/comment/best"
OUTPUT = ROOT / "results/kold-classifier/dktc-gap-v1"


def protected_texts(paths):
    """Texts of every evaluation set, including the project's final split."""
    texts = set()
    for name in ("context_eval.jsonl", "realistic_comments.jsonl"):
        with (ROOT / "data" / name).open(encoding="utf-8") as stream:
            texts.update(normalized(json.loads(line)["text"]) for line in stream
                         if line.strip() and json.loads(line).get("split") == "final")
    for path in paths:
        if path.exists():
            with path.open(encoding="utf-8") as stream:
                texts.update(normalized(json.loads(line)["text"]) for line in stream if line.strip())
    return texts


def load_approved(paths, protected=PROTECTED_EVAL):
    rows = []
    for path in paths:
        with path.open(encoding="utf-8") as stream:
            rows.extend(json.loads(line) for line in stream if line.strip())
    if not rows:
        raise ValueError("No approved comments")
    ids = set()
    texts = set()
    held_out = dev_texts() | protected_texts(protected)
    counts = Counter()
    statuses = Counter()
    for row in rows:
        if row.get("reviewStatus") not in {"approved", "codex_provisional"} or row.get("expectedAction") not in {"PASS", "BLOCK"}:
            raise ValueError(f"Invalid review status or label: {row.get('id')}")
        if row.get("split") in EVAL_SPLITS:
            raise ValueError(f"Evaluation split row cannot be used for training: {row.get('id')}")
        text = normalized(row["text"])
        if not text or text in texts or text in held_out or row["id"] in ids:
            raise ValueError(f"Duplicate, empty, or development text: {row['id']}")
        ids.add(row["id"])
        texts.add(text)
        counts[row["expectedAction"]] += 1
        statuses[row["reviewStatus"]] += 1
    if counts["BLOCK"] < 10 or counts["PASS"] < 10:
        raise ValueError("Exploratory adaptation requires at least 10 BLOCK and 10 PASS examples")
    return rows, counts, statuses


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approved", type=Path, nargs="+", default=[APPROVED],
                        help="One or more reviewed/provisional JSONL files; texts must be unique across files")
    parser.add_argument("--protected-eval", type=Path, nargs="*", default=PROTECTED_EVAL,
                        help="Evaluation JSONL files whose texts must not appear in training")
    parser.add_argument("--kold-dir", type=Path, default=KOLD)
    parser.add_argument("--base-model", type=Path, default=BASE)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    parser.add_argument("--replay-per-class", type=int, default=500)
    parser.add_argument("--approved-repeat", type=int, default=12)
    parser.add_argument("--epochs", type=float, default=1.0)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=5e-6)
    parser.add_argument("--seed", type=int, default=17)
    args = parser.parse_args()
    if args.replay_per_class < 1 or args.approved_repeat < 1 or args.epochs <= 0:
        parser.error("Replay count, repeat count, and epochs must be positive")
    if args.output_dir.exists():
        parser.error(f"Output already exists; choose a new output directory: {args.output_dir}")
    if args.output_dir.resolve() == args.base_model.resolve():
        parser.error("Output directory must differ from the original checkpoint")

    approved, counts, statuses = load_approved(args.approved, args.protected_eval)
    replay_rows, _ = select_rows(args.kold_dir / "train.jsonl")
    by_label = {label: [row for row, target in replay_rows if target == label]
                for label in (0, 1)}
    if any(len(by_label[label]) < args.replay_per_class for label in (0, 1)):
        raise ValueError("Not enough KOLD replay rows")
    rng = random.Random(args.seed)
    train_rows = []
    for label in (0, 1):
        train_rows.extend((row["text"], label) for row in
                          rng.sample(by_label[label], args.replay_per_class))
    train_rows.extend((row["text"], int(row["expectedAction"] == "BLOCK"))
                      for row in approved for _ in range(args.approved_repeat))
    rng.shuffle(train_rows)
    validation, _ = select_rows(args.kold_dir / "validation.jsonl")
    validation_rows = [(row["text"], label) for row, label in validation]
    if {label for _, label in validation_rows} != {0, 1}:
        raise ValueError("KOLD validation needs both classes")

    # Import ML dependencies only after all data and output checks pass.
    import torch
    from torch.utils.data import Dataset
    from transformers import (AutoModelForSequenceClassification, AutoTokenizer,
                              DataCollatorWithPadding, Trainer, TrainingArguments)

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    tokenizer = AutoTokenizer.from_pretrained(args.base_model, use_fast=True)
    base_config = json.loads((args.base_model / "stage2_config.json").read_text(encoding="utf-8"))
    if base_config.get("mode") != "comment":
        raise ValueError("Base checkpoint must be a comment-only classifier")
    max_length = base_config["maxLength"]

    class CommentDataset(Dataset):
        def __init__(self, items):
            self.items = items

        def __len__(self):
            return len(self.items)

        def __getitem__(self, index):
            comment, label = self.items[index]
            return tokenizer(comment, truncation=True, max_length=max_length) | {"labels": label}

    model = AutoModelForSequenceClassification.from_pretrained(args.base_model)
    settings = TrainingArguments(
        output_dir=str(args.output_dir / "checkpoints"),
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        greater_is_better=True,
        save_total_limit=2,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size * 2,
        learning_rate=args.learning_rate,
        warmup_ratio=0.05,
        weight_decay=0.01,
        logging_strategy="epoch",
        report_to="none",
        seed=args.seed,
        data_seed=args.seed,
        dataloader_num_workers=0,
        dataloader_pin_memory=False,
    )
    trainer = Trainer(
        model=model,
        args=settings,
        train_dataset=CommentDataset(train_rows),
        eval_dataset=CommentDataset(validation_rows),
        data_collator=DataCollatorWithPadding(tokenizer),
        processing_class=tokenizer,
        compute_metrics=metrics,
    )
    trainer.train()
    best = args.output_dir / "best"
    trainer.save_model(str(best))
    tokenizer.save_pretrained(best)
    base_config.pop("testMetrics", None)
    base_config.update({
        "baseModel": str(args.base_model),
        "adaptation": "DKTC gap candidates with KOLD replay",
        "approvedCounts": dict(counts),
        "reviewStatuses": dict(statuses),
        "replayPerClass": args.replay_per_class,
        "approvedRepeat": args.approved_repeat,
        "label0": "KOLD OFF=false plus reviewed PASS examples",
        "label1": "KOLD targeted offense plus reviewed BLOCK examples",
        "epochs": args.epochs,
        "learningRate": args.learning_rate,
        "seed": args.seed,
        "bestCheckpoint": trainer.state.best_model_checkpoint,
        "warning": ("Exploratory adaptation; Codex-provisional labels are not human approved"
                    if statuses["codex_provisional"] else
                    "Exploratory adaptation; evaluate on unchanged stage-one PASS dev set"),
    })
    (best / "stage2_config.json").write_text(
        json.dumps(base_config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"savedModel": str(best), "approvedCounts": dict(counts)},
                     ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
