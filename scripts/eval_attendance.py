"""Score the attendance planner against tests/fixtures/attendance_eval.json."""
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

from sqlalchemy import exc
import logging

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.model_inference import generate_plan, load_model
from backend.services.llm_chat_service import (
    PlanRejectedError,
    correct_plan,
    resolve_context,
)

# Debug logging: shows why the validator rejects a plan.
logging.basicConfig(level=logging.WARNING)
logging.getLogger("backend.services.model_inference").setLevel(logging.DEBUG)

EVAL_PATH = PROJECT_ROOT / "tests" / "fixtures" / "attendance_eval.json"
TODAY = date(2026, 11, 18)
EVAL_PATH = PROJECT_ROOT / "tests" / "fixtures" / "attendance_eval.json"
TODAY = date(2026, 11, 18)

EVAL_PATH = "tests/fixtures/attendance_eval.json"
TODAY = date(2026, 11, 18)

def score_case(c, meta):
    try:
        raw = generate_plan(c["question"])
    except PlanRejectedError as exc:
        print(f"REJECTED {c['id']}: {exc}")
        raw = {"operation_id": None, "filters": {}, "rejected": True}

    exp = c["expected_raw"]
    raw_non_date = {k: v for k, v in raw.get("filters", {}).items() if k != "attendance_date"}
    exp_non_date = {k: v for k, v in exp.get("filters", {}).items() if k != "attendance_date"}
    raw_op_ok = raw.get("operation_id") == exp["operation_id"]
    raw_filters_ok = raw_non_date == exp_non_date
    raw_date_ok = raw.get("filters", {}).get("attendance_date") == exp.get("filters", {}).get("attendance_date")

    final = None
    final_ok = True
    if c.get("expected_final"):
        if raw.get("operation_id") is None:
            final_ok = False
        else:
            normalized = resolve_context(c["question"])
            final, _ = correct_plan(
                raw, c["question"], normalized,
                meta["employee_id"], meta["organization_id"], TODAY,
            )
            final_ok = final == c["expected_final"] or (
                final.get("operation_id") == c["expected_final"]["operation_id"]
                and final.get("filters", {}) == c["expected_final"]["filters"]
                and final.get("aggregate_field") == c["expected_final"].get("aggregate_field")
            )

    passed = final_ok if c.get("expected_final") else raw_op_ok
    return passed, {"raw_op_ok": raw_op_ok, "raw_filters_ok": raw_filters_ok,
                    "raw_date_ok": raw_date_ok, "raw": raw}, final

def main():
    load_model() 
    with open(EVAL_PATH, encoding="utf-8") as f:
        data = json.load(f)
    meta = data["meta"]

    groups = defaultdict(lambda: [0, 0])
    failures = []

    for c in data["cases"]:
        passed, raw, final = score_case(c, meta)
        groups[c["group"]][0] += passed
        groups[c["group"]][1] += 1
        if not passed:
            failures.append((c, raw, final))

    passed_total = sum(p for p, _ in groups.values())
    total = sum(t for _, t in groups.values())
    print(f"Overall: {passed_total}/{total} = {passed_total / total:.0%}\n")
    for group, (p, t) in sorted(groups.items()):
        print(f"  {group}: {p}/{t}")

    for c, raw, final in failures:
        print(f"\nFAIL {c['id']}: {c['question']}")
        print(f"  model raw: {raw}")
        if final is not None:
            print(f"  corrected: {final}")
        print(f"  expected:  {c.get('expected_final') or c['expected_raw']}")

if __name__ == "__main__":
    main()