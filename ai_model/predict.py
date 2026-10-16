import torch
from ai_model.model import TickoraTransformer
from ai_model.tokenizer import SimpleTokenizer
from ai_model.parameter_extractor import parse_request

CHECKPOINT_PATH = "data/artifacts/tickora_intent_model.pt"
MAX_LENGTH = 64

def load_model():
    checkpoint = torch.load(
        CHECKPOINT_PATH,
        map_location="cpu",
        weights_only=True,
    )

    tokenizer = SimpleTokenizer()
    tokenizer.token_to_id = checkpoint["token_to_id"]
    tokenizer.id_to_token = {
        int(key): value
        for key, value in checkpoint["id_to_token"].items()
    }

    model = TickoraTransformer(**checkpoint["model_config"])
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()

    return model, tokenizer, checkpoint["intents"]


def predict(question, model, tokenizer, intents):
    token_ids = tokenizer.encode(question)[:MAX_LENGTH]

    if not token_ids:
        raise ValueError("Please enter a non-empty question.")

    input_ids = torch.tensor([token_ids], dtype=torch.long)

    with torch.no_grad():
        logits = model(input_ids)
        probabilities = torch.softmax(logits, dim=1)[0]

    predicted_id = int(probabilities.argmax())
    confidence = float(probabilities[predicted_id])

    return intents[predicted_id], confidence


def process_question(question, model, tokenizer, intents):
    # Step 1: Predict the intent using the trained Transformer.
    intent, confidence = predict(
        question, model, tokenizer, intents
    )

    # Step 2: Extract parameters and validate the request.
    result = parse_request(question, intent)

    return intent, confidence, result

def main():
    model, tokenizer, intents = load_model()

    print("Tickora AI request processing test")
    print("Type 'exit' to quit.\n")

    while True:
        question = input("Ask Tickora: ").strip()

        if question.lower() == "exit":
            break

        if not question:
            print("Please enter a question.\n")
            continue

        try:
            intent, confidence, result = process_question(
                question, model, tokenizer, intents
            )

            print(f"Predicted intent: {intent}")
            print(f"Model confidence: {confidence:.2%}")

            if isinstance(result, dict):
                if "error" in result:
                    print(f"Parameter validation error: {result['error']}")
                else:
                    print("Validated request:")
                    print(result)
            else:
                print("Validated request:")
                print(result.model_dump(mode="json"))

            print()

        except (ValueError, RuntimeError) as exc:
            print(f"Could not process question: {exc}\n")


if __name__ == "__main__":
    main()
