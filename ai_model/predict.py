import torch
from ai_model.model import TickoraTransformer
from ai_model.tokenizer import SimpleTokenizer

CHECKPOINT_PATH = "data/artifacts/tickora_intent_model.pt"

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
    token_ids = tokenizer.encode(question)[:64]

    if not token_ids:
        raise ValueError("Please enter a non-empty question.")

    input_ids = torch.tensor([token_ids], dtype=torch.long)

    with torch.no_grad():
        logits = model(input_ids)
        probabilities = torch.softmax(logits, dim=1)[0]

    predicted_id = int(probabilities.argmax())
    confidence = float(probabilities[predicted_id])

    return intents[predicted_id], confidence

def main():
    model, tokenizer, intents = load_model()

    print("Tickora intent prediction test")
    print("Type 'exit' to quit.\n")

    while True:
        question = input("Ask Tickora: ").strip()

        if question.lower() == "exit":
            break

        if not question:
            print("Please enter a question.\n")
            continue

        intent, confidence = predict(
            question, model, tokenizer, intents
        )

        print(f"Predicted intent: {intent}")
        print(f"Model confidence: {confidence:.2%}\n")


if __name__ == "__main__":
    main()
