# import json
# import random
# from pathlib import Path

# import torch
# import torch.nn as nn
# from torch.utils.data import DataLoader, Dataset

# from ai_model.model import TickoraTransformer
# from ai_model.tokenizer import SimpleTokenizer

# # Paths
# TRAIN_PATH = Path("data/splits/train.jsonl")
# VAL_PATH = Path("data/splits/validation.jsonl")
# ARTIFACT_DIR = Path("data/artifacts")
# CHECKPOINT_PATH = ARTIFACT_DIR / "tickora_intent_model.pt"

# # Reproducible experiment settings
# SEED = 42
# BATCH_SIZE = 8
# EPOCHS = 20
# LEARNING_RATE = 0.001
# MAX_LENGTH = 64

# EARLY_STOPPING_PATIENCE = 4
# MIN_IMPROVEMENT = 0.01


# # Stable class IDs: do not change this order after training.
# INTENTS = [
#     "attendance_records",
#     "attendance_summary",
#     "holiday_lookup",
#     "leave_status",
#     "schedule_lookup",
#     "timesheet_lookup",
#     "wfh_status",
# ]

# def set_seed(seed: int) -> None:
#     random.seed(seed)
#     torch.manual_seed(seed)

# def load_jsonl(path: Path) -> list[dict]:
#     with path.open("r", encoding="utf-8") as file:
#         return [json.loads(line) for line in file if line.strip()]
# class IntentDataset(Dataset):
#     def __init__(self, examples, tokenizer, label_to_id):
#         self.examples = examples
#         self.tokenizer = tokenizer
#         self.label_to_id = label_to_id

#     def __len__(self):
#         return len(self.examples)

#     def __getitem__(self, index):
#         example = self.examples[index]
#         text = example["text"]
#         intent = example["target"]["intent"]

#         token_ids = self.tokenizer.encode(text)[:MAX_LENGTH]

#         return (
#             torch.tensor(token_ids, dtype=torch.long),
#             torch.tensor(self.label_to_id[intent], dtype=torch.long),
#         )

# def collate_batch(batch):
#     sequences, labels = zip(*batch)

#     max_len = max(len(sequence) for sequence in sequences)
#     max_len = max(max_len, 1)

#     input_ids = torch.zeros(
#         len(sequences), max_len, dtype=torch.long
#     )

#     for index, sequence in enumerate(sequences):
#         input_ids[index, :len(sequence)] = sequence

#     labels = torch.stack(labels)
#     return input_ids, labels

# def evaluate(model, loader, criterion, device):
#     model.eval()
#     total_loss = 0.0
#     total_correct = 0
#     total_examples = 0

#     with torch.no_grad():
#         for input_ids, labels in loader:
#             input_ids = input_ids.to(device)
#             labels = labels.to(device)

#             logits = model(input_ids)
#             loss = criterion(logits, labels)

#             batch_size = labels.size(0)
#             total_loss += loss.item() * batch_size
#             total_correct += (logits.argmax(dim=1) == labels).sum().item()
#             total_examples += batch_size

#     return (
#         total_loss / max(total_examples, 1),
#         total_correct / max(total_examples, 1),
#     )

# def main():
#     set_seed(SEED)
    

#     if not TRAIN_PATH.exists() or not VAL_PATH.exists():
#         raise FileNotFoundError(
#             "Dataset splits not found. Run "
#             "'uv run python -m ai_model.prepare_dataset' first."
#         )

#     train_examples = load_jsonl(TRAIN_PATH)
#     val_examples = load_jsonl(VAL_PATH)

#     if not train_examples or not val_examples:
#         raise ValueError("Training and validation datasets must not be empty.")

#     unknown_intents = {
#         example["target"]["intent"]
#         for example in train_examples + val_examples
#         if example["target"]["intent"] not in INTENTS
#     }
#     if unknown_intents:
#         raise ValueError(f"Unknown intent labels: {unknown_intents}")

#     # Fit vocabulary only on training questions.
#     tokenizer = SimpleTokenizer()
#     tokenizer.fit([example["text"] for example in train_examples])

#     label_to_id = {intent: index for index, intent in enumerate(INTENTS)}

#     train_dataset = IntentDataset(
#         train_examples, tokenizer, label_to_id
#     )
#     val_dataset = IntentDataset(
#         val_examples, tokenizer, label_to_id
#     )

#     train_loader = DataLoader(
#         train_dataset,
#         batch_size=BATCH_SIZE,
#         shuffle=True,
#         collate_fn=collate_batch,
#     )
#     val_loader = DataLoader(
#         val_dataset,
#         batch_size=BATCH_SIZE,
#         shuffle=False,
#         collate_fn=collate_batch,
#     )

#     device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
#     model = TickoraTransformer(
#         vocab_size=tokenizer.vocab_size,
#         num_classes=len(INTENTS),
#         max_length=MAX_LENGTH,
#     ).to(device)

#     criterion = nn.CrossEntropyLoss()
#     optimizer = torch.optim.AdamW(
#         model.parameters(),
#         lr=LEARNING_RATE,
#     )

#     ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
#     best_val_loss = float("inf")
#     epochs_without_improvement = 0

#     print(f"Device: {device}")
#     print(f"Training examples: {len(train_dataset)}")
#     print(f"Validation examples: {len(val_dataset)}")
#     print(f"Vocabulary size: {tokenizer.vocab_size}")
#     print(f"Number of classes: {len(INTENTS)}")
#     print(f"Model parameters: {sum(p.numel() for p in model.parameters()):,}")

#     for epoch in range(1, EPOCHS + 1):
#         model.train()
#         total_train_loss = 0.0
#         total_train_examples = 0

#         for input_ids, labels in train_loader:
#             input_ids = input_ids.to(device)
#             labels = labels.to(device)

#             optimizer.zero_grad(set_to_none=True)

#             logits = model(input_ids)
#             loss = criterion(logits, labels)

#             loss.backward()
#             torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
#             optimizer.step()

#             batch_size = labels.size(0)
#             total_train_loss += loss.item() * batch_size
#             total_train_examples += batch_size

#         train_loss = total_train_loss / total_train_examples
#         val_loss, val_accuracy = evaluate(
#             model, val_loader, criterion, device
#         )

#         print(
#             f"Epoch {epoch:02d}/{EPOCHS} | "
#             f"train_loss={train_loss:.4f} | "
#             f"val_loss={val_loss:.4f} | "
#             f"val_accuracy={val_accuracy:.2%}"
#         )

        
#         if val_loss < best_val_loss - MIN_IMPROVEMENT:
#             best_val_loss = val_loss
#             epochs_without_improvement = 0

#             torch.save(
#                 {
#                     "model_state_dict": model.state_dict(),
#                     "model_config": {
#                         "vocab_size": tokenizer.vocab_size,
#                         "num_classes": len(INTENTS),
#                         "max_length": MAX_LENGTH,
#                         "d_model": 128,
#                         "n_heads": 4,
#                         "n_layers": 2,
#                         "dropout": 0.1,
#                     },
#                     "token_to_id": tokenizer.token_to_id,
#                     "id_to_token": {
#                         str(key): value
#                         for key, value in tokenizer.id_to_token.items()
#                     },
#                     "intents": INTENTS,
#                     "label_to_id": label_to_id,
#                     "best_val_loss": best_val_loss,
#                     "epoch": epoch,
#                 },
#                 CHECKPOINT_PATH,
#             )
#             print(f"  Saved best checkpoint: {CHECKPOINT_PATH}")
#         else:
#             epochs_without_improvement += 1

#         if epochs_without_improvement >= EARLY_STOPPING_PATIENCE:
#             print(f"Early stopping at epoch {epoch}.")
#             break


#     print("\nTraining complete.")
#     print(f"Best validation loss: {best_val_loss:.4f}")
#     print(f"Checkpoint: {CHECKPOINT_PATH}")

# if __name__ == "__main__":
#     main()


import json
import random
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

from ai_model.model import TickoraTransformer
from ai_model.tokenizer import SimpleTokenizer


# --------------------------------------------------
# Paths
# --------------------------------------------------

TRAIN_PATH = Path("data/splits/train.jsonl")
VAL_PATH = Path("data/splits/validation.jsonl")

ARTIFACT_DIR = Path("data/artifacts")
CHECKPOINT_PATH = ARTIFACT_DIR / "tickora_intent_model.pt"


# --------------------------------------------------
# Reproducible experiment settings
# --------------------------------------------------

SEED = 42
BATCH_SIZE = 8
EPOCHS = 20
LEARNING_RATE = 0.001
MAX_LENGTH = 64

EARLY_STOPPING_PATIENCE = 4
MIN_IMPROVEMENT = 0.01


# --------------------------------------------------
# Stable intent labels
# Keep this order consistent with inference/evaluation.
# --------------------------------------------------

INTENTS = [
    "attendance_records",
    "attendance_summary",
    "holiday_lookup",
    "leave_status",
    "schedule_lookup",
    "timesheet_lookup",
    "wfh_status",
]


# --------------------------------------------------
# Reproducibility
# --------------------------------------------------

def set_seed(seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)

    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


# --------------------------------------------------
# Dataset loading
# --------------------------------------------------

def load_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as file:
        return [
            json.loads(line)
            for line in file
            if line.strip()
        ]


class IntentDataset(Dataset):
    def __init__(self, examples, tokenizer, label_to_id):
        self.examples = examples
        self.tokenizer = tokenizer
        self.label_to_id = label_to_id

    def __len__(self):
        return len(self.examples)

    def __getitem__(self, index):
        example = self.examples[index]

        text = example["text"]
        intent = example["target"]["intent"]

        token_ids = self.tokenizer.encode(text)[:MAX_LENGTH]

        return (
            torch.tensor(token_ids, dtype=torch.long),
            torch.tensor(
                self.label_to_id[intent],
                dtype=torch.long,
            ),
        )


# --------------------------------------------------
# Batch padding
# --------------------------------------------------

def collate_batch(batch):
    sequences, labels = zip(*batch)

    max_len = max(
        max(len(sequence) for sequence in sequences),
        1,
    )

    input_ids = torch.zeros(
        len(sequences),
        max_len,
        dtype=torch.long,
    )

    for index, sequence in enumerate(sequences):
        input_ids[index, :len(sequence)] = sequence

    labels = torch.stack(labels)

    return input_ids, labels


# --------------------------------------------------
# Validation
# --------------------------------------------------

def evaluate(model, loader, criterion, device):
    model.eval()

    total_loss = 0.0
    total_correct = 0
    total_examples = 0

    with torch.no_grad():
        for input_ids, labels in loader:
            input_ids = input_ids.to(device)
            labels = labels.to(device)

            logits = model(input_ids)
            loss = criterion(logits, labels)

            batch_size = labels.size(0)

            total_loss += loss.item() * batch_size
            total_correct += (
                logits.argmax(dim=1) == labels
            ).sum().item()

            total_examples += batch_size

    average_loss = total_loss / max(total_examples, 1)
    accuracy = total_correct / max(total_examples, 1)

    return average_loss, accuracy


# --------------------------------------------------
# Checkpoint saving
# --------------------------------------------------

def save_checkpoint(
    model,
    tokenizer,
    label_to_id,
    best_val_loss,
    epoch,
):
    checkpoint = {
        "model_state_dict": model.state_dict(),
        "model_config": {
            "vocab_size": tokenizer.vocab_size,
            "num_classes": len(INTENTS),
            "max_length": MAX_LENGTH,
            "d_model": 128,
            "n_heads": 4,
            "n_layers": 2,
            "dropout": 0.1,
        },
        "token_to_id": tokenizer.token_to_id,
        "id_to_token": {
            str(key): value
            for key, value in tokenizer.id_to_token.items()
        },
        "intents": INTENTS,
        "label_to_id": label_to_id,
        "best_val_loss": best_val_loss,
        "epoch": epoch,
    }

    torch.save(checkpoint, CHECKPOINT_PATH)

    print(f"  Saved best checkpoint: {CHECKPOINT_PATH}")


# --------------------------------------------------
# Main training function
# --------------------------------------------------

def main():
    set_seed(SEED)

    # Verify dataset files exist.
    if not TRAIN_PATH.exists() or not VAL_PATH.exists():
        raise FileNotFoundError(
            "Dataset splits not found. Run "
            "'uv run python -m ai_model.prepare_merged_dataset' first."
        )

    train_examples = load_jsonl(TRAIN_PATH)
    val_examples = load_jsonl(VAL_PATH)

    if not train_examples or not val_examples:
        raise ValueError(
            "Training and validation datasets must not be empty."
        )

    # Validate intent labels.
    unknown_intents = {
        example["target"]["intent"]
        for example in train_examples + val_examples
        if example["target"]["intent"] not in INTENTS
    }

    if unknown_intents:
        raise ValueError(
            f"Unknown intent labels: {unknown_intents}"
        )

    # Verify that every intent occurs in both splits.
    for split_name, examples in [
        ("training", train_examples),
        ("validation", val_examples),
    ]:
        present_intents = {
            example["target"]["intent"]
            for example in examples
        }

        missing_intents = set(INTENTS) - present_intents

        if missing_intents:
            raise ValueError(
                f"Missing intents in {split_name} data: "
                f"{sorted(missing_intents)}"
            )

    # Fit the vocabulary only on training questions.
    tokenizer = SimpleTokenizer()
    tokenizer.fit([
        example["text"]
        for example in train_examples
    ])

    label_to_id = {
        intent: index
        for index, intent in enumerate(INTENTS)
    }

    train_dataset = IntentDataset(
        train_examples,
        tokenizer,
        label_to_id,
    )

    val_dataset = IntentDataset(
        val_examples,
        tokenizer,
        label_to_id,
    )

    train_loader = DataLoader(
        train_dataset,
        batch_size=BATCH_SIZE,
        shuffle=True,
        collate_fn=collate_batch,
    )

    val_loader = DataLoader(
        val_dataset,
        batch_size=BATCH_SIZE,
        shuffle=False,
        collate_fn=collate_batch,
    )

    # Use GPU when available; otherwise use CPU.
    device = torch.device(
        "cuda" if torch.cuda.is_available() else "cpu"
    )

    # New model initialization: no pretrained weights are loaded.
    model = TickoraTransformer(
        vocab_size=tokenizer.vocab_size,
        num_classes=len(INTENTS),
        max_length=MAX_LENGTH,
    ).to(device)

    criterion = nn.CrossEntropyLoss()

    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=LEARNING_RATE,
    )

    ARTIFACT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Absolute best loss determines which checkpoint is saved.
    best_val_loss = float("inf")
    best_significant_val_loss = float("inf")
    best_epoch = 0
    epochs_without_improvement = 0

    print("=" * 55)
    print("TICKORA TRANSFORMER TRAINING")
    print("=" * 55)
    print(f"Device: {device}")
    print(f"Training examples: {len(train_dataset)}")
    print(f"Validation examples: {len(val_dataset)}")
    print(f"Vocabulary size: {tokenizer.vocab_size}")
    print(f"Number of classes: {len(INTENTS)}")
    print(
        "Model parameters: "
        f"{sum(p.numel() for p in model.parameters()):,}"
    )
    print(f"Maximum epochs: {EPOCHS}")
    print(f"Early-stopping patience: {EARLY_STOPPING_PATIENCE}")
    print(f"Minimum loss improvement: {MIN_IMPROVEMENT}")
    print("=" * 55)

    # --------------------------------------------------
    # Training loop
    # --------------------------------------------------

    for epoch in range(1, EPOCHS + 1):
        model.train()

        total_train_loss = 0.0
        total_train_examples = 0

        for input_ids, labels in train_loader:
            input_ids = input_ids.to(device)
            labels = labels.to(device)

            optimizer.zero_grad(set_to_none=True)

            logits = model(input_ids)
            loss = criterion(logits, labels)

            loss.backward()

            torch.nn.utils.clip_grad_norm_(
                model.parameters(),
                max_norm=1.0,
            )

            optimizer.step()

            batch_size = labels.size(0)

            total_train_loss += loss.item() * batch_size
            total_train_examples += batch_size

        train_loss = (
            total_train_loss
            / max(total_train_examples, 1)
        )

        val_loss, val_accuracy = evaluate(
            model,
            val_loader,
            criterion,
            device,
        )

        print(
            f"Epoch {epoch:02d}/{EPOCHS} | "
            f"train_loss={train_loss:.4f} | "
            f"val_loss={val_loss:.4f} | "
            f"val_accuracy={val_accuracy:.2%}"
        )

        # Save every new absolute best checkpoint.
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_epoch = epoch

            save_checkpoint(
                model=model,
                tokenizer=tokenizer,
                label_to_id=label_to_id,
                best_val_loss=best_val_loss,
                epoch=best_epoch,
            )

        # Early stopping uses significant improvements.
        if (
            val_loss
            < best_significant_val_loss - MIN_IMPROVEMENT
        ):
            best_significant_val_loss = val_loss
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1

        if epochs_without_improvement >= EARLY_STOPPING_PATIENCE:
            print(
                f"\nEarly stopping at epoch {epoch}. "
                "Validation loss stopped improving sufficiently."
            )
            break

    print("\n" + "=" * 55)
    print("TRAINING COMPLETE")
    print("=" * 55)
    print(f"Best validation loss: {best_val_loss:.4f}")
    print(f"Best checkpoint epoch: {best_epoch}")
    print(f"Checkpoint: {CHECKPOINT_PATH}")
    print("=" * 55)


if __name__ == "__main__":
    main()
