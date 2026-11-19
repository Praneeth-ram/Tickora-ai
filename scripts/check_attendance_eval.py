"""Check tests/fixtures/attendance_eval.json before scoring the model."""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.model_inference import _load_catalog

EVAL_PATH = "tests/fixtures/attendance_eval.json"
TRAIN_PATH = "data/splits/train.jsonl"

def check_against_catalog(cases, catalog):
    errors = []
    for c in cases:
        for key in ("expected_raw", "expected_final"):
            plan = c.get(key)
            if not plan:
                continue
            op = plan.get("operation_id")
            if op is None:
                # Out-of-scope case: the planner should produce no operation.
                if plan.get("filters"):
                    errors.append(f"{c['id']}: out-of-scope case must have empty filters")
                continue
            if op not in catalog:
                errors.append(f"{c['id']}: unknown operation {op!r}")
                continue
            allowed = set(catalog[op].get("filters", []))
            extra = set(plan.get("filters", {})) - allowed
            if extra:
                errors.append(f"{c['id']}: filters not allowed for {op}: {sorted(extra)}")
    return errors

def check_train_overlap(cases):
    train = set()
    with open(TRAIN_PATH, encoding="utf-8") as f:
        for line in f:
            msgs = json.loads(line)["messages"]
            user = next(m["content"] for m in msgs if m["role"] == "user")
            train.add(user.strip().lower())
    return [
        f"{c['id']}: question also in training data"
        for c in cases
        if c["question"].strip().lower() in train
    ]

def main():
    with open(EVAL_PATH, encoding="utf-8") as f:
        data = json.load(f)
    cases = data["cases"]
    catalog = _load_catalog()

    errors = check_against_catalog(cases, catalog) + check_train_overlap(cases)
    if errors:
        print("Problems found:")
        for e in errors:
            print(" -", e)
        sys.exit(1)
    print(f"OK: {len(cases)} cases, consistent with catalog, no training overlap.")


if __name__ == "__main__":
    main()