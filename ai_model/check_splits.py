import json
from collections import Counter
from pathlib import Path

split_names = ["train", "validation", "test"]
all_intents = set()

for name in split_names:
    path = Path(f"data/splits/{name}.jsonl")

    with path.open("r", encoding="utf-8") as file:
        rows = [json.loads(line) for line in file if line.strip()]

    counts = Counter(row["target"]["intent"] for row in rows)
    all_intents.update(counts)

    print(f"\n{name.upper()}: {len(rows)} examples")
    for intent, count in sorted(counts.items()):
        print(f"  {intent}: {count}")

    print(f"Intents represented: {len(counts)} / 7")

print(f"\nTotal intents found: {len(all_intents)}")
print("Split verification complete.")
