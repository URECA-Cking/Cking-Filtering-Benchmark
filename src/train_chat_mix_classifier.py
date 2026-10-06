"""Train KcELECTRA on KOLD plus a sampled, cleaned chat-profanity set.

Controlled comparison with the KOLD-only checkpoint: same base model, same KOLD
validation/test splits, same KOLD label rule. The chat set is exploratory
(CC BY-NC-SA 4.0, coarse profanity labels). No threat/stalking data is mixed in
here, so any change comes from the chat data alone.
"""

import argparse
import json
import random
from pathlib import Path

from src.train_dktc_gap_classifier import PROTECTED_EVAL, protected_texts
from src.train_kold_classifier import metrics, read_jsonl, select_rows
from src.validate_dktc_review_sheet import normalized


ROOT = Path(__file__).resolve().parents[1]
KOLD = ROOT / "data/restricted/kold"
CHAT = ROOT / "data/restricted/chat_profanity"
OUTPUT = ROOT / "results/kold-classifier/chat-mix-v1"
BASE_MODEL = "beomi/KcELECTRA-base"


def load_chat(path, blocked):
    rows = [(row["text"], row["label"]) for row in read_jsonl(path)]
    if not rows or {label for _, label in rows} != {0, 1}:
        raise ValueError(f"{path} needs both labels")
    leaked = [text for text, _ in rows if normalized(text) in blocked]
    if leaked:
        raise ValueError(f"Chat rows overlap protected evaluation text: {leaked[0]}")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kold-dir", type=Path, default=KOLD)
    parser.add_argument("--chat-dir", type=Path, default=CHAT)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    parser.add_argument("--base-model", default=BASE_MODEL)
    parser.add_argument("--kold-repeat", type=int, default=3,
                        help="Repeat KOLD train rows so targeted-offense data is not drowned out")
    parser.add_argument("--chat-label1-fraction", type=float, default=1.0,
                        help="Share of chat label-1 rows to use; 0 keeps only chat label-0 rows as extra PASS data")
    parser.add_argument("--group-by-length", action="store_true",
                        help="Batch similar-length rows together to cut padding (faster; changes batch order)")
    parser.add_argument("--epochs", type=float, default=2.0)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--max-length", type=int, default=128)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--seed", type=int, default=17)
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error(f"Output already exists; choose a new directory: {args.output_dir}")
    if args.kold_repeat < 1 or args.epochs <= 0 or not 0 <= args.chat_label1_fraction <= 1:
        parser.error("Repeat count and epochs must be positive; label-1 fraction must be in [0, 1]")

    blocked = protected_texts(PROTECTED_EVAL)
    kold_train = [(row["text"], label) for row, label in select_rows(args.kold_dir / "train.jsonl")[0]]
    kold_validation = [(row["text"], label) for row, label in select_rows(args.kold_dir / "validation.jsonl")[0]]
    kold_test = [(row["text"], label) for row, label in select_rows(args.kold_dir / "test.jsonl")[0]]
    # Chat rows must not repeat any KOLD validation/test text, including rows the label rule drops.
    blocked = blocked | {normalized(row["text"]) for name in ("validation", "test")
                         for row in read_jsonl(args.kold_dir / f"{name}.jsonl")}
    chat_train = load_chat(args.chat_dir / "train.jsonl", blocked)
    chat_validation = load_chat(args.chat_dir / "validation.jsonl", blocked)
    keep = random.Random(args.seed + 1)
    chat_train = [(text, label) for text, label in chat_train
                  if label == 0 or keep.random() < args.chat_label1_fraction]
    train_rows = kold_train * args.kold_repeat + chat_train
    random.Random(args.seed).shuffle(train_rows)
    print(json.dumps({"koldTrain": len(kold_train), "koldRepeat": args.kold_repeat,
                      "chatTrain": len(chat_train), "chatLabel1": sum(l for _, l in chat_train),
                      "total": len(train_rows)}), flush=True)

    # Heavy dependencies load only after all data checks pass.
    import torch
    from torch.utils.data import Dataset
    from transformers import (AutoModelForSequenceClassification, AutoTokenizer,
                              DataCollatorWithPadding, Trainer, TrainingArguments)

    torch.manual_seed(args.seed)
    tokenizer = AutoTokenizer.from_pretrained(args.base_model, use_fast=True)

    class CommentDataset(Dataset):
        def __init__(self, rows):
            self.labels = [label for _, label in rows]
            self.encodings = {}
            texts = [text for text, _ in rows]
            for start in range(0, len(texts), 2048):
                batch = tokenizer(texts[start:start + 2048], truncation=True,
                                  max_length=args.max_length, padding=False)
                for key, values in batch.items():
                    self.encodings.setdefault(key, []).extend(values)

        def __len__(self):
            return len(self.labels)

        def __getitem__(self, index):
            return {key: values[index] for key, values in self.encodings.items()} | {
                "labels": self.labels[index]}

    model = AutoModelForSequenceClassification.from_pretrained(
        args.base_model, num_labels=2,
        id2label={0: "NORMAL", 1: "TARGETED_OFFENSE"},
        label2id={"NORMAL": 0, "TARGETED_OFFENSE": 1})
    settings = TrainingArguments(
        output_dir=str(args.output_dir / "checkpoints"),
        eval_strategy="epoch", save_strategy="epoch",
        load_best_model_at_end=True, metric_for_best_model="f1", greater_is_better=True,
        save_total_limit=2, num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size * 2,
        learning_rate=args.learning_rate, warmup_ratio=0.06, weight_decay=0.01,
        fp16=torch.cuda.is_available(), group_by_length=args.group_by_length,
        logging_steps=200, report_to="none",
        seed=args.seed, data_seed=args.seed,
        dataloader_num_workers=0, dataloader_pin_memory=False)
    trainer = Trainer(
        model=model, args=settings, train_dataset=CommentDataset(train_rows),
        eval_dataset=CommentDataset(kold_validation),  # same selection rule as the KOLD-only run
        data_collator=DataCollatorWithPadding(tokenizer),
        processing_class=tokenizer, compute_metrics=metrics)
    trainer.train()
    kold_test_metrics = trainer.evaluate(CommentDataset(kold_test), metric_key_prefix="test")
    chat_validation_metrics = trainer.evaluate(CommentDataset(chat_validation),
                                               metric_key_prefix="chat_validation")
    best = args.output_dir / "best"
    trainer.save_model(str(best))
    tokenizer.save_pretrained(best)
    config = {
        "baseModel": args.base_model, "mode": "comment", "maxLength": args.max_length,
        "seed": args.seed, "label0": "KOLD OFF=false plus chat label 0",
        "label1": "KOLD targeted offense plus chat label 1 (coarse profanity)",
        "koldRepeat": args.kold_repeat, "chatTrainRows": len(chat_train),
        "chatLabel1Fraction": args.chat_label1_fraction, "groupByLength": args.group_by_length,
        "epochs": args.epochs, "learningRate": args.learning_rate,
        "bestCheckpoint": trainer.state.best_model_checkpoint,
        "testMetrics": kold_test_metrics, "chatValidationMetrics": chat_validation_metrics,
        "warning": ("Exploratory: chat data is CC BY-NC-SA 4.0 with coarse labels; "
                    "not approved for service use"),
    }
    (best / "stage2_config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"savedModel": str(best), "koldTest": kold_test_metrics,
                      "chatValidation": chat_validation_metrics}, ensure_ascii=False, indent=2),
          flush=True)


if __name__ == "__main__":
    main()
