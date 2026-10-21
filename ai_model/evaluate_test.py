
import json
from pathlib import Path
from collections import Counter, defaultdict

from ai_model.predict import load_model, predict

TEST_PATH = Path("data/splits/test.jsonl")


def get_question(record):
    for key in ("text", "question", "query", "input"):
        if isinstance(record.get(key), str):
            return record[key]
    raise ValueError(f"Could not find question text in: {record}")


def get_label(record):
    target = record.get("target", record.get("label", record.get("intent")))

    if isinstance(target, dict):
        target = target.get("intent")

    if not isinstance(target, str):
        raise ValueError(f"Could not find target intent in: {record}")

    return target


def main():
    if not TEST_PATH.exists():
        raise FileNotFoundError(f"Test file not found: {TEST_PATH}")

    records = [
        json.loads(line)
        for line in TEST_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    model, tokenizer, intents = load_model()
    confusion = {actual: Counter() for actual in intents}
    actual_counts = Counter()
    predicted_counts = Counter()
    mistakes = []
    correct = 0

    for record in records:
        question = get_question(record)
        actual = get_label(record)

        if actual not in intents:
            raise ValueError(f"Unknown intent '{actual}' in test data.")

        predicted, confidence = predict(
            question, model, tokenizer, intents
        )

        actual_counts[actual] += 1
        predicted_counts[predicted] += 1
        confusion[actual][predicted] += 1

        if predicted == actual:
            correct += 1
        else:
            mistakes.append(
                (question, actual, predicted, confidence)
            )

    total = len(records)
    accuracy = correct / total if total else 0.0

    print("\n" + "=" * 72)
    print("TICKORA INTENT CLASSIFIER — HELD-OUT TEST RESULTS")
    print("=" * 72)
    print(f"Test examples : {total}")
    print(f"Correct       : {correct}")
    print(f"Incorrect     : {total - correct}")
    print(f"Accuracy      : {accuracy:.2%}")

    print("\nPER-INTENT METRICS")
    print("-" * 72)
    print(f"{'Intent':<24} {'Precision':>10} {'Recall':>10} {'F1':>10} {'Support':>9}")

    f1_values = []
    weighted_f1 = 0.0

    for intent in intents:
        tp = confusion[intent][intent]
        fp = predicted_counts[intent] - tp
        fn = actual_counts[intent] - tp

        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall else 0.0
        )
        support = actual_counts[intent]

        f1_values.append(f1)
        weighted_f1 += f1 * support

        print(
            f"{intent:<24} {precision:>9.2%} "
            f"{recall:>9.2%} {f1:>9.2%} {support:>9}"
        )

    macro_f1 = sum(f1_values) / len(f1_values) if f1_values else 0.0
    weighted_f1 = weighted_f1 / total if total else 0.0

    print("-" * 72)
    print(f"Macro F1     : {macro_f1:.2%}")
    print(f"Weighted F1  : {weighted_f1:.2%}")

    print("\nCONFUSION MATRIX")
    print("Rows = actual intent; columns = predicted intent")
    print("Column order:", " | ".join(intents))
    for actual in intents:
        values = [str(confusion[actual][pred]) for pred in intents]
        print(f"{actual:<24} " + " | ".join(values))

    print("\nMISCLASSIFIED QUESTIONS")
    print("-" * 72)
    if not mistakes:
        print("No misclassified questions.")
    else:
        for question, actual, predicted, confidence in mistakes:
            print(f"\nQuestion : {question}")
            print(f"Actual   : {actual}")
            print(f"Predicted: {predicted}")
            print(f"Confidence: {confidence:.2%}")

    print("\nEvaluation complete. No model weights were modified.")


if __name__ == "__main__":
    main()
