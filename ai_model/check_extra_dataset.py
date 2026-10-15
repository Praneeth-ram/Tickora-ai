
import json
from collections import Counter
from pathlib import Path

from ai_model.intents import IntentRequest

PATH = Path("data/intent_dataset_extra.jsonl")


def main():
    examples = []
    errors = []

    with PATH.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue

            try:
                row = json.loads(line)

                if set(row) != {"text", "target"}:
                    raise ValueError("Expected only text and target fields")

                if not isinstance(row["text"], str) or not row["text"].strip():
                    raise ValueError("Question text must not be empty")

                target = IntentRequest.model_validate(row["target"])
                examples.append({
                    "text": row["text"].strip(),
                    "intent": target.intent,
                })
            except Exception as exc:
                errors.append(f"Line {line_number}: {exc}")

    if errors:
        print("VALIDATION ERRORS:")
        print("\n".join(errors))
        raise SystemExit(1)

    print("Additional examples:", len(examples))
    print("Intent distribution:")
    for intent, count in sorted(
        Counter(row["intent"] for row in examples).items()
    ):
        print(f"  {intent}: {count}")

    print("Extra dataset validation passed.")


if __name__ == "__main__":
    main()
