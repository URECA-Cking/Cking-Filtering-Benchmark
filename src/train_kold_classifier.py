"""Fine-tune a Korean comment classifier on local, prepared KOLD data.

KOLD OFF is a training proxy. This script does not touch the project's
context_eval/realistic_comments development or final splits.
"""

import argparse
import json
import random
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data/restricted/kold"
OUTPUT_DIR = ROOT / "results/kold-classifier/comment"
BASE_MODEL = "beomi/KcELECTRA-base"


def read_jsonl(path):
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def training_label(row):
    """Targeted KOLD offense is closer to our stage-two abuse/hate policy.

    Untargeted and 'other' offenses are excluded for this first experiment:
    many concern profanity or targets outside the current stage-two goal.
    """
    if not row["offensive"]:
        return 0
    if row["targetType"] in ("individual", "group"):
        return 1
    return None


def select_rows(path):
    selected = []
    excluded = Counter()
    for row in read_jsonl(path):
        label = training_label(row)
        if label is None:
            excluded[str(row["targetType"])] += 1
            continue
        selected.append((row, label))
    return selected, excluded


def metrics(prediction):
    import numpy as np

    logits = prediction.predictions
    if isinstance(logits, tuple):
        logits = logits[0]
    predicted = np.argmax(logits, axis=1)
    actual = prediction.label_ids
    tp = int(np.sum((predicted == 1) & (actual == 1)))
    fp = int(np.sum((predicted == 1) & (actual == 0)))
    fn = int(np.sum((predicted == 0) & (actual == 1)))
    tn = int(np.sum((predicted == 0) & (actual == 0)))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1,
            "false_positive_rate": fp / (fp + tn) if fp + tn else 0.0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--base-model", default=BASE_MODEL)
    parser.add_argument("--epochs", type=float, default=3.0)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-length", type=int, default=192)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--threads", type=int, default=8)
    args = parser.parse_args()
    output_dir = args.output_dir

    # Heavy dependencies are loaded only when the user explicitly runs training.
    import torch
    from torch.utils.data import Dataset
    from transformers import (
        AutoModelForSequenceClassification,
        AutoTokenizer,
        DataCollatorWithPadding,
        Trainer,
        TrainingArguments,
    )

    torch.manual_seed(args.seed)
    torch.set_num_threads(args.threads)
    random.seed(args.seed)
    parts = {}
    for name in ("train", "validation", "test"):
        parts[name], excluded = select_rows(args.data_dir / f"{name}.jsonl")
        print(name, "selected", len(parts[name]),
              "normal", sum(label == 0 for _, label in parts[name]),
              "targeted_offense", sum(label == 1 for _, label in parts[name]),
              "excluded", dict(excluded), flush=True)
        if not parts[name] or {label for _, label in parts[name]} != {0, 1}:
            raise ValueError(f"{name} needs both labels")

    tokenizer = AutoTokenizer.from_pretrained(args.base_model, use_fast=True)

    class CommentDataset(Dataset):
        def __init__(self, rows):
            self.labels = [label for _, label in rows]
            comments = [row["text"] for row, _ in rows]
            self.encodings = {}
            for start in range(0, len(rows), 1024):
                end = start + 1024
                batch = tokenizer(
                    comments[start:end],
                    truncation=True,
                    max_length=args.max_length,
                    padding=False,
                )
                for key, values in batch.items():
                    self.encodings.setdefault(key, []).extend(values)

        def __len__(self):
            return len(self.labels)

        def __getitem__(self, index):
            return {key: values[index] for key, values in self.encodings.items()} | {
                "labels": self.labels[index]
            }

    datasets = {
        name: CommentDataset(rows)
        for name, rows in parts.items()
    }
    model = AutoModelForSequenceClassification.from_pretrained(
        args.base_model,
        num_labels=2,
        id2label={0: "NORMAL", 1: "TARGETED_OFFENSE"},
        label2id={"NORMAL": 0, "TARGETED_OFFENSE": 1},
    )
    settings = TrainingArguments(
        output_dir=str(output_dir / "checkpoints"),
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
        warmup_ratio=0.1,
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
        train_dataset=datasets["train"],
        eval_dataset=datasets["validation"],
        data_collator=DataCollatorWithPadding(tokenizer),
        processing_class=tokenizer,
        compute_metrics=metrics,
    )
    trainer.train()
    test_metrics = trainer.evaluate(datasets["test"], metric_key_prefix="test")
    best_dir = output_dir / "best"
    trainer.save_model(str(best_dir))
    tokenizer.save_pretrained(best_dir)
    metadata = {
        "baseModel": args.base_model,
        "mode": "comment",
        "maxLength": args.max_length,
        "seed": args.seed,
        "label0": "KOLD OFF=false",
        "label1": "KOLD OFF=true and TGT in {individual,group}",
        "excludedOffenseTargets": ["untargeted", "other"],
        "warning": "KOLD labels are a training proxy, not the service BLOCK policy",
        "bestCheckpoint": trainer.state.best_model_checkpoint,
        "testMetrics": test_metrics,
    }
    (best_dir / "stage2_config.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"savedModel": str(best_dir), "testMetrics": test_metrics},
                     ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
