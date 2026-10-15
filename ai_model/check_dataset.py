import json
from collections import Counter
from pathlib import Path
from ai_model.intents import IntentRequest

DATASET_PATH = Path("data/intent_dataset.jsonl")

def main():
    examples = []
    errors = []

    with DATASET_PATH.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if set(row) != {"text", "target"}:
                    raise ValueError("Each row must contain only text and target")
                if not isinstance(row["text"], str) or not row["text"].strip():
                    raise ValueError("text must be a non-empty string")

                target = IntentRequest.model_validate(row["target"])
                examples.append({
                    "text": row["text"].strip(),
                    "target": target,
                })
            except Exception as exc:
                errors.append(f"Line {line_number}: {exc}")

    if errors:
        print("DATASET ERRORS:")
        print("\n".join(errors))
        raise SystemExit(1)

    print(f"Total examples: {len(examples)}")
    print("Intent distribution:")

    for intent, count in sorted(
        Counter(row["target"].intent for row in examples).items()
    ):
        print(f"  {intent}: {count}")

    print("Dataset validation passed.")

if __name__ == "__main__":
    main()
