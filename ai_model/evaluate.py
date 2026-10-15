import json
from pathlib import Path
import torch
from ai_model.model import TickoraTransformer
from ai_model.tokenizer import SimpleTokenizer

TEST_PATH = Path("data/splits/test.jsonl")
CHECKPOINT_PATH = Path("data/artifacts/tickora_intent_model.pt")

def main():
    checkpoint = torch.load(
        CHECKPOINT_PATH,
        map_location="cpu",
        weights_only=True,
    )

    intents = checkpoint["intents"]
    label_to_id = checkpoint["label_to_id"]

    tokenizer = SimpleTokenizer()
    tokenizer.token_to_id = checkpoint["token_to_id"]
    tokenizer.id_to_token = {
        int(key): value
        for key, value in checkpoint["id_to_token"].items()
    }

    model = TickoraTransformer(**checkpoint["model_config"])
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()

    with TEST_PATH.open("r", encoding="utf-8") as file:
        examples = [
            json.loads(line)
            for line in file
            if line.strip()
        ]

    if not examples:
        raise ValueError("Test dataset is empty.")

    # Rows = actual intents; columns = predicted intents.
    confusion = [
        [0 for _ in intents]
        for _ in intents
    ]

    correct = 0
    total = 0

    print("TICKORA TEST EVALUATION\n")

    with torch.no_grad():
        for example in examples:
            question = example["text"]
            actual_intent = example["target"]["intent"]
            actual_id = label_to_id[actual_intent]

            token_ids = tokenizer.encode(question)[:64]
            if not token_ids:
                token_ids = [tokenizer.token_to_id["<UNK>"]]

            input_ids = torch.tensor(
                [token_ids],
                dtype=torch.long,
            )

            logits = model(input_ids)
            probabilities = torch.softmax(logits, dim=1)[0]
            predicted_id = int(probabilities.argmax())
            predicted_intent = intents[predicted_id]
            confidence = float(probabilities[predicted_id])

            is_correct = predicted_id == actual_id
            correct += int(is_correct)
            total += 1
            confusion[actual_id][predicted_id] += 1

            result = "CORRECT" if is_correct else "WRONG"
            print(f"Question: {question}")
            print(f"  Actual:    {actual_intent}")
            print(f"  Predicted: {predicted_intent}")
            print(f"  Confidence: {confidence:.2%}")
            print(f"  Result: {result}\n")

    print("=" * 60)
    print(f"Test examples: {total}")
    print(f"Correct: {correct}")
    print(f"Incorrect: {total - correct}")
    print(f"Test accuracy: {correct / total:.2%}")

    print("\nPER-INTENT RESULTS")
    for index, intent in enumerate(intents):
        actual_count = sum(confusion[index])
        class_correct = confusion[index][index]
        accuracy = (
            class_correct / actual_count
            if actual_count
            else 0.0
        )
        print(
            f"{intent}: {class_correct}/{actual_count} "
            f"correct ({accuracy:.2%})"
        )

    print("\nCONFUSION MATRIX")
    print("Rows = actual | Columns = predicted")
    print("Intent order:", intents)

    for intent, row in zip(intents, confusion):
        print(f"{intent}: {row}")

if __name__ == "__main__":
    main()
