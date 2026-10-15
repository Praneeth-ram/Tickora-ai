import torch
from ai_model.model import TickoraTransformer

def main():
    torch.manual_seed(42)

    model = TickoraTransformer(
        vocab_size=100,
        num_classes=7,
    )

    # Simulate two tokenized questions, padded to length 5.
    input_ids = torch.tensor([
        [74, 54, 15, 89, 0],
        [23, 18, 0, 0, 0],
    ])

    logits = model(input_ids)

    print("Input shape:", tuple(input_ids.shape))
    print("Output shape:", tuple(logits.shape))
    print("Predicted class IDs:", logits.argmax(dim=1).tolist())

    assert logits.shape == (2, 7)
    assert torch.isfinite(logits).all()

    print("Transformer model tests passed.")

if __name__ == "__main__":
    main()
