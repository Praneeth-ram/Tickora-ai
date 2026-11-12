"""Create leakage-resistant train/validation/test splits for Tickora SFT JSONL.

Run from repository root:
    python scripts/split_tickora_dataset.py

Rows sharing an identical assistant query plan are assigned to the same split.
This is stricter than random row splitting but can reduce coverage of rare plans
in train, so inspect the printed coverage before training.
"""
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

SOURCE = Path("data/tickora_sft.jsonl")
OUT_DIR = Path("data/splits")
SEED = 42
TRAIN_RATIO = 0.80
VAL_RATIO = 0.10
TEST_RATIO = 0.10

if abs(TRAIN_RATIO + VAL_RATIO + TEST_RATIO - 1.0) > 1e-9:
    raise ValueError("Split ratios must sum to 1.0")

rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines() if line.strip()]
if not rows:
    raise ValueError(f"No examples found in {SOURCE}")

def message_content(row, role):
    matches = [m.get("content", "") for m in row.get("messages", []) if m.get("role") == role]
    if len(matches) != 1:
        raise ValueError(f"Each row must contain exactly one {role} message")
    return matches[0]

def plan_key(row):
    raw = message_content(row, "assistant")
    try:
        plan = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Assistant target is not valid JSON: {raw}") from exc
    return json.dumps(plan, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

# Group all paraphrases with the same target plan, within each operation.
# Stratifying by operation ensures every operation can appear in every split
# when it has at least three distinct query-plan patterns.
groups_by_operation = defaultdict(list)
for row in rows:
    plan = json.loads(message_content(row, "assistant"))
    key = json.dumps(plan, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    groups_by_operation[plan["operation_id"]].append((key, row))

names = ["train", "validation", "test"]
splits = [[], [], []]
split_group_keys = [set(), set(), set()]
rng = random.Random(SEED)

for op_id in sorted(groups_by_operation):
    grouped = defaultdict(list)
    for key, row in groups_by_operation[op_id]:
        grouped[key].append(row)
    items = list(grouped.items())
    rng.shuffle(items)
    items.sort(key=lambda item: len(item[1]), reverse=True)

    # Seed each split with one unique target-plan group where possible.
    local = [[], [], []]
    local_keys = [set(), set(), set()]
    if len(items) >= 3:
        for i in range(3):
            key, group = items.pop()
            local[i].extend(group)
            local_keys[i].add(key)

    # Assign remaining groups to the split furthest below its target size.
    total_rows = sum(len(group) for group in grouped.values())
    local_targets = [total_rows * TRAIN_RATIO, total_rows * VAL_RATIO, total_rows * TEST_RATIO]
    for key, group in items:
        idx = min(
            range(3),
            key=lambda i: (len(local[i]) / max(local_targets[i], 1), len(local[i]), i),
        )
        local[idx].extend(group)
        local_keys[idx].add(key)

    for i in range(3):
        splits[i].extend(local[i])
        split_group_keys[i].update(local_keys[i])

for i, name in enumerate(names):
    rng.shuffle(splits[i])
    path = OUT_DIR / f"{name}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for row in splits[i]:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    counts = Counter(json.loads(message_content(row, "assistant"))["operation_id"] for row in splits[i])
    print(f"\n{name}: {len(splits[i])} examples -> {path}")
    print(f"  operations represented: {len(counts)} / 12")
    for op_id, count in sorted(counts.items()):
        print(f"  {op_id}: {count}")

# Prove that exact target plans are not shared between splits.
keys_by_split = [
    {plan_key(row) for row in split_rows}
    for split_rows in splits
]
for i in range(3):
    for j in range(i + 1, 3):
        overlap = keys_by_split[i] & keys_by_split[j]
        if overlap:
            raise RuntimeError(f"Target-plan leakage between {names[i]} and {names[j]}: {len(overlap)} plans")

print("\nLeakage check: no identical assistant query plans cross splits.")
print(f"Total: {sum(map(len, splits))} / {len(rows)} examples")
print("Review operation coverage above. If an operation is missing from validation/test, use a curated held-out set covering every operation before model evaluation.")
