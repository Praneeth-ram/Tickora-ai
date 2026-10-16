import torch
from ai_model.model import TickoraTransformer
from ai_model.tokenizer import SimpleTokenizer
from ai_model.parameter_extractor import parse_request
import re

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


OUT_OF_SCOPE_PATTERNS = [
    r"\b(?:tell|say|make|write)\s+me\s+a\s+joke\b",
    r"\bweather\s+(?:today|tomorrow|forecast)\b",
    r"\bwho\s+is\s+the\s+president\b",
    r"\bsolve\s+(?:this\s+)?coding\s+problem\b",
    r"\bwrite\s+(?:me\s+)?(?:a\s+)?(?:python|javascript|java)\s+program\b",
    r"\b(?:what|which)\s+(?:is|are)\s+my\s+(?:department|dept|team)\b",
    r"\b(?:department|dept)\b",
    r"\b(?:salary|payroll|payslip|pay\s*slip|compensation|ctc)\b",
    r"\b(?:who\s+is\s+my|my)\s+(?:manager|boss|supervisor|lead)\b",
    r"\b(?:performance|appraisal|promotion|bonus)\b",
    r"\b(?:what\s+is\s+my|my)\s+(?:designation|job\s*title|role)\b",
]


def is_clearly_out_of_scope(question: str) -> bool:
    """Detect a few clearly unrelated requests before intent classification."""
    normalized = question.strip().lower()
    return any(
        re.search(pattern, normalized)
        for pattern in OUT_OF_SCOPE_PATTERNS
    )

def process_question(question, model, tokenizer, intents):
    # Reject clearly unrelated questions before model classification.
    if is_clearly_out_of_scope(question):
        return "out_of_scope", 1.0, {
            "error": "This question is outside Tickora AI's scope.",
            "details": [],
        }

    intent, confidence = predict(
        question, model, tokenizer, intents
    )

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
