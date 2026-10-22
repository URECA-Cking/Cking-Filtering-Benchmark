"""Extract review candidates from DKTC training conversations; assign no labels."""

import argparse
import csv
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data/raw/dktc/data/train.csv"
DEFAULT_OUTPUT = ROOT / "data/restricted/dktc/threat_candidates.jsonl"
ALL_CLASS_OUTPUT = ROOT / "data/restricted/dktc/all_class_candidates.jsonl"
SOURCE = "DKTC train.csv (tunib-ai/DKTC, CC BY-NC-SA 4.0)"

# A broad retrieval filter, not a threat classifier or a BLOCK label.
THREAT_CUES = {
    "physical_harm": re.compile(r"죽여|죽일|살해|찌르|패버|때려|폭행|불질러|불을\s*지르|폭발물|폭탄|가만\s*안\s*(?:둘|둬)|해치"),
    "implicit_threat": re.compile(r"두고\s*봐|각오해|각오하|후회하게|후회할|끝장|무사하지|재미없을|어떻게\s*되는지"),
    "stalking_or_exposure": re.compile(r"집\s*주소|주소.{0,8}알|찾아가|찾아낼|따라다니|지켜보|전화번호.{0,8}알"),
}
WHITESPACE = re.compile(r"\s+")
PHONE = re.compile(r"(?<!\d)(?:\+?82[- .]?)?0?1[016789](?:[- .]?\d){7,8}(?!\d)")
EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
IDENTITY = re.compile(r"(?<!\d)\d{6}[- ]?[1-4]\d{6}(?!\d)")
ADDRESS_HINT = re.compile(r"(?:시|군|구)\s*[가-힣0-9]+(?:동|읍|면|로|길)\s*\d|(?:로|길)\s*\d+(?:[- ]\d+)?")


def normalize(value):
    return WHITESPACE.sub(" ", unicodedata.normalize("NFC", value)).strip()


def redact(text):
    flags = []
    for name, pattern in (("identity", IDENTITY), ("phone", PHONE), ("email", EMAIL)):
        text, count = pattern.subn("[REDACTED]", text)
        if count:
            flags.append(name)
    if ADDRESS_HINT.search(text):
        flags.append("possible_address")
    return text, flags


def extract_candidates(rows, all_classes=False):
    seen_ids = set()
    counts = Counter()
    candidates = []
    for row in rows:
        if set(row) != {"idx", "class", "conversation"}:
            raise ValueError("Expected DKTC train.csv columns: idx,class,conversation")
        conversation_id = row["idx"]
        if conversation_id in seen_ids:
            raise ValueError(f"Duplicate conversation ID: {conversation_id}")
        seen_ids.add(conversation_id)
        counts[row["class"]] += 1
        if not all_classes and row["class"] != "협박 대화":
            continue
        for turn_index, raw_turn in enumerate(row["conversation"].splitlines(), start=1):
            turn = normalize(raw_turn)
            # Short reactions and long multi-sentence monologues are unlikely
            # to be useful as independent, single-comment examples.
            if not 12 <= len(turn) <= 250:
                continue
            cues = [name for name, pattern in THREAT_CUES.items() if pattern.search(turn)]
            if not cues:
                continue
            safe_text, privacy_flags = redact(turn)
            candidates.append({
                "id": f"dktc-train-{conversation_id}-{turn_index}",
                "source": SOURCE,
                "conversationId": conversation_id,
                "conversationClass": row["class"],
                "turnIndex": turn_index,
                "text": safe_text,
                "cueTypes": cues,
                "privacyFlags": privacy_flags,
                "reviewStatus": "pending_human",
                "expectedAction": None,
                "notes": "",
            })
    return candidates, counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--all-classes", action="store_true",
                        help="Also retrieve lines from extortion and bullying conversations")
    args = parser.parse_args()
    output = args.output or (ALL_CLASS_OUTPUT if args.all_classes else DEFAULT_OUTPUT)
    if args.input.resolve() == output.resolve():
        parser.error("Input and output paths must differ")
    with args.input.open(encoding="utf-8-sig", newline="") as stream:
        candidates, classes = extract_candidates(csv.DictReader(stream), args.all_classes)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as stream:
        for candidate in candidates:
            stream.write(json.dumps(candidate, ensure_ascii=False) + "\n")
    print(json.dumps({
        "inputConversations": sum(classes.values()),
        "threatConversations": classes["협박 대화"],
        "candidateTurns": len(candidates),
        "candidateConversations": len({row["conversationId"] for row in candidates}),
        "candidateClasses": dict(Counter(row["conversationClass"] for row in candidates)),
        "privacyFlaggedTurns": sum(bool(row["privacyFlags"]) for row in candidates),
        "output": str(output),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
