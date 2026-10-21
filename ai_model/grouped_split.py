
import json
import random
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

SOURCE = Path("data/intent_dataset_merged.jsonl")
OUTPUT = Path("data/grouped_splits")

SEED = 42
TRAIN_RATIO = 0.70
VAL_RATIO = 0.15

# Conservative lexical similarity thresholds.
JACCARD_THRESHOLD = 0.70
SEQUENCE_THRESHOLD = 0.88

INTENTS = [
    "attendance_records",
    "attendance_summary",
    "holiday_lookup",
    "leave_status",
    "schedule_lookup",
    "timesheet_lookup",
    "wfh_status",
]


def normalize(text):
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))

def tokens(text):
    return set(normalize(text).split())

def similar(text_a, text_b):
    a = tokens(text_a)
    b = tokens(text_b)

    if not a or not b:
        return False

    jaccard = len(a & b) / len(a | b)
    sequence = SequenceMatcher(
        None, normalize(text_a), normalize(text_b)
    ).ratio()

    return (
        jaccard >= JACCARD_THRESHOLD
        or sequence >= SEQUENCE_THRESHOLD
    )

def find_groups(records):
    # Union-find groups similar questions, including transitive matches.
    parent = list(range(len(records)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        root_a = find(a)
        root_b = find(b)
        if root_a != root_b:
            parent[root_b] = root_a

    normalized = [
        normalize(record["text"]) for record in records
    ]

    # Exact duplicates are grouped efficiently first.
    first_seen = {}
    for index, text in enumerate(normalized):
        if text in first_seen:
            union(index, first_seen[text])
        else:
            first_seen[text] = index

    # Compare pairs with similar lengths to reduce unnecessary comparisons.
    order = sorted(
        range(len(records)),
        key=lambda i: len(normalized[i]),
    )

    for position, index_a in enumerate(order):
        text_a = normalized[index_a]

        for index_b in order[position + 1:]:
            text_b = normalized[index_b]

            if len(text_b) > max(1, len(text_a)) * 2.0:
                break

            intent_a = records[index_a]["target"]["intent"]
            intent_b = records[index_b]["target"]["intent"]

            if intent_a == intent_b and similar(text_a, text_b):
                union(index_a, index_b)

    groups = {}
    for index in range(len(records)):
        groups.setdefault(find(index), []).append(index)

    return list(groups.values())

def group_intent_counts(group, records):
    return Counter(
        records[index]["target"]["intent"]
        for index in group
    )

def assign_groups(groups, records):
    rng = random.Random(SEED)
    groups = list(groups)
    rng.shuffle(groups)

    # Place larger groups first to make balancing more stable.
    groups.sort(key=len, reverse=True)

    total = Counter(
        record["target"]["intent"] for record in records
    )
    targets = {
        "train": Counter(),
        "validation": Counter(),
        "test": Counter(),
    }
    ratios = {
        "train": TRAIN_RATIO,
        "validation": VAL_RATIO,
        "test": 1 - TRAIN_RATIO - VAL_RATIO,
    }

    assigned = {
        "train": [],
        "validation": [],
        "test": [],
    }

    for group in groups:
        counts = group_intent_counts(group, records)

        def cost(split):
            score = 0.0
            for intent in INTENTS:
                desired = total[intent] * ratios[split]
                after = targets[split][intent] + counts[intent]
                score += ((after - desired) / max(1, total[intent])) ** 2
            return score

        # Prefer the split with the lowest current deviation from its target.
        chosen = min(
            assigned.keys(),
            key=lambda split: cost(split) + (
                len(assigned[split]) / max(1, len(groups))
            ) * 0.01,
        )

        assigned[chosen].append(group)
        targets[chosen].update(counts)

    return {
        split: [
            records[index]
            for group in split_groups
            for index in group
        ]
        for split, split_groups in assigned.items()
    }

def write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")

def main():
    if not SOURCE.exists():
        raise FileNotFoundError(f"Missing source dataset: {SOURCE}")

    records = [
        json.loads(line)
        for line in SOURCE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    for record in records:
        if (
            not isinstance(record.get("text"), str)
            or not isinstance(record.get("target"), dict)
            or record["target"].get("intent") not in INTENTS
        ):
            raise ValueError(f"Invalid dataset record: {record}")

    groups = find_groups(records)
    label_conflicts = []

    for group in groups:
        labels = {
            records[index]["target"]["intent"]
            for index in group
        }
        if len(labels) > 1:
            label_conflicts.append((group, labels))

    print("=" * 64)
    print("TICKORA GROUPED-SPLIT AUDIT")
    print("=" * 64)
    print(f"Examples: {len(records)}")
    print(f"Similarity groups: {len(groups)}")
    print(f"Groups with multiple examples: {sum(len(g) > 1 for g in groups)}")
    print(f"Largest group: {max(map(len, groups), default=0)}")
    print(f"Groups with conflicting intents: {len(label_conflicts)}")

    for group, labels in label_conflicts[:20]:
        print(f"\nPOSSIBLE LABEL CONFLICT: {sorted(labels)}")
        for index in group:
            print(
                f"  [{records[index]['target']['intent']}] "
                f"{records[index]['text']}"
            )

    # Export a review report so similarity thresholds can be audited.
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with (OUTPUT / "groups_review.jsonl").open(
        "w", encoding="utf-8"
    ) as file:
        for group_id, group in enumerate(groups):
            if len(group) > 1:
                item = {
                    "group_id": group_id,
                    "examples": [
                        records[index] for index in group
                    ],
                }
                file.write(json.dumps(item, ensure_ascii=False) + "\n")

    if label_conflicts:
        print(
            "\nSTOP: Review conflicting-label groups before using "
            "these splits for model evaluation."
        )
        print(f"Review file: {OUTPUT / 'groups_review.jsonl'}")
        return

    splits = assign_groups(groups, records)

    for split_name, split_records in splits.items():
        write_jsonl(
            OUTPUT / f"{split_name}.jsonl",
            split_records,
        )
        print(
            f"{split_name:10}: {len(split_records):3} examples | "
            f"{dict(Counter(r['target']['intent'] for r in split_records))}"
        )

    print(f"\nNew splits written to: {OUTPUT}")
    print("Original data/splits files were not modified.")
    print(
        "Review groups_review.jsonl and confirm that all intents "
        "are represented before training."
    )


if __name__ == "__main__":
    main()
