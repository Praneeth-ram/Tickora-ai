
# import json
# import re
# from collections import Counter
# from pathlib import Path

# from ai_model.intents import IntentRequest

# FILES = [
#     Path("data/intent_dataset.jsonl"),
#     Path("data/intent_dataset_extra.jsonl"),
# ]
# OUTPUT = Path("data/intent_dataset_merged.jsonl")


# def normalize(text: str) -> str:
#     return re.sub(r"\s+", " ", text.strip().lower())


# def main():
#     merged = {}
#     duplicates = 0

#     for path in FILES:
#         with path.open("r", encoding="utf-8") as file:
#             for line_number, line in enumerate(file, start=1):
#                 if not line.strip():
#                     continue

#                 row = json.loads(line)

#                 if set(row) != {"text", "target"}:
#                     raise ValueError(f"Invalid fields in {path}:{line_number}")

#                 if not isinstance(row["text"], str) or not row["text"].strip():
#                     raise ValueError(f"Empty question in {path}:{line_number}")

#                 target = IntentRequest.model_validate(row["target"])
#                 key = normalize(row["text"])

#                 if key in merged:
#                     previous = merged[key]["target"].intent

#                     if previous != target.intent:
#                         raise ValueError(
#                             f"Conflicting labels for question: {row['text']!r}\n"
#                             f"Existing: {previous}; new: {target.intent}"
#                         )

#                     duplicates += 1
#                     continue

#                 merged[key] = {
#                     "text": row["text"].strip(),
#                     "target": target.model_dump(mode="json", exclude_none=True),
#                 }

#     examples = list(merged.values())
#     OUTPUT.parent.mkdir(parents=True, exist_ok=True)

#     with OUTPUT.open("w", encoding="utf-8") as file:
#         for example in examples:
#             file.write(json.dumps(example, ensure_ascii=False) + "\n")

#     print("Original + extra examples:", 130)
#     print("Exact/normalized duplicates removed:", duplicates)
#     print("Unique examples:", len(examples))
#     print("Intent distribution:")

#     counts = Counter(row["target"]["intent"] for row in examples)
#     for intent, count in sorted(counts.items()):
#         print(f"  {intent}: {count}")

#     print(f"Merged dataset saved to: {OUTPUT}")


# if __name__ == "__main__":
#     main()

import json
import re
from collections import Counter
from pathlib import Path

from ai_model.intents import IntentRequest

FILES = [
    Path("data/intent_dataset.jsonl"),
    Path("data/intent_dataset_extra.jsonl"),
    Path("data/intent_dataset_expansion.jsonl"),
    Path("data/intent_dataset_contrastive.jsonl"),
    Path("data/intent_dataset_contrastive_v2.jsonl"),
    Path("data/intent_dataset_contrastive_v3.jsonl"),
]
OUTPUT = Path("data/intent_dataset_merged.jsonl")


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def main():
    merged = {}
    duplicates = 0

    for path in FILES:
        if not path.exists():
            raise FileNotFoundError(f"Dataset file not found: {path}")
        with path.open("r", encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                if not line.strip():
                    continue
                row = json.loads(line)
                if set(row) != {"text", "target"}:
                    raise ValueError(f"Invalid fields in {path}:{line_number}")
                if not isinstance(row["text"], str) or not row["text"].strip():
                    raise ValueError(f"Empty question in {path}:{line_number}")

                target = IntentRequest.model_validate(row["target"])
                key = normalize(row["text"])
                if key in merged:
                    previous_target = merged[key]["target"]
                    if previous_target != target.model_dump(mode="json", exclude_none=True):
                        raise ValueError(
                            f"Conflicting targets for duplicate question: {row['text']!r} "
                            f"({path}:{line_number})"
                        )
                    duplicates += 1
                    continue

                merged[key] = {
                    "text": row["text"].strip(),
                    "target": target.model_dump(mode="json", exclude_none=True),
                }

    examples = list(merged.values())
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8") as file:
        for example in examples:
            file.write(json.dumps(example, ensure_ascii=False) + "\n")

    print("Duplicate questions removed:", duplicates)
    print("Unique examples:", len(examples))
    print("Intent distribution:")
    for intent, count in sorted(Counter(r["target"]["intent"] for r in examples).items()):
        print(f"  {intent}: {count}")
    print(f"Merged dataset saved to: {OUTPUT}")


if __name__ == "__main__":
    main()

