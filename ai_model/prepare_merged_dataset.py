import json
import random
from collections import defaultdict
from pathlib import Path

SOURCE = Path("data/intent_dataset_merged.jsonl")
OUTPUT_DIR = Path("data/splits")
SEED = 42

def main():
    groups = defaultdict(list)

    with SOURCE.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                groups[json.loads(line)["target"]["intent"]].append(
                    json.loads(line)
                )

    rng = random.Random(SEED)
    train, validation, test = [], [], []

    for intent, examples in sorted(groups.items()):
        rng.shuffle(examples)
        n = len(examples)

        n_train = round(n * 0.70)
        n_validation = round(n * 0.15)

        # Ensure all examples are assigned exactly once.
        train.extend(examples[:n_train])
        validation.extend(examples[n_train:n_train + n_validation])
        test.extend(examples[n_train + n_validation:])

    for name, examples in [
        ("train", train),
        ("validation", validation),
        ("test", test),
    ]:
        rng.shuffle(examples)
        path = OUTPUT_DIR / f"{name}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("w", encoding="utf-8") as file:
            for example in examples:
                file.write(json.dumps(example, ensure_ascii=False) + "\n")

        print(f"{name}: {len(examples)} examples")

    print(f"Total: {len(train) + len(validation) + len(test)}")

if __name__ == "__main__":
    main()
