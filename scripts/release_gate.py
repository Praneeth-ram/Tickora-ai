import json
import sys
from datetime import date

from backend.services.llm_chat_service import (
    ModelServiceError,
    PlanRejectedError,
    normalize_and_correct_plan,
    plan_question,
)
from backend.services.model_inference import fingerprint, generate_plan, load_model

GOLDEN_PATH = "tests/fixtures/golden_plans.json"
GATE_TODAY = date(2026, 11, 11)  # fixed, so date-based plans do not drift daily
KNOWN_MODEL_ISSUES = {"How many holidays are there in 2026?"}


def main() -> int:
    load_model()

    with open(GOLDEN_PATH, encoding="utf-8") as file:
        golden = json.load(file)

    if golden.get("fingerprint") != fingerprint():
        print("Fingerprint mismatch: regenerate the golden plans for this model.")
        print("  saved:  ", golden.get("fingerprint"))
        print("  current:", fingerprint())
        return 2

    plans = golden.get("plans")
    if plans is None:
        plans = golden.get("live_plans", golden.get("model_plans"))
    if plans is None:
        raise ValueError("Golden file must contain a 'plans' mapping.")

    model_changed = []
    live_changed = []
    live_plans = {}
    unavailable = []

    for question, expected in plans.items():
        try:
            raw_model = generate_plan(question)
            actual, _period = normalize_and_correct_plan(
                raw_model, question, GATE_TODAY
            )
        except PlanRejectedError:
            actual = {"rejected": True}
        if actual != expected:
            model_changed.append((question, expected, actual))

        try:
            raw = plan_question(question)
            final, _period = normalize_and_correct_plan(raw, question, GATE_TODAY)
        except ModelServiceError:
            unavailable.append(question)
            continue

        live_plans[question] = final
        if final != expected:
            live_changed.append((question, expected, final))

    if "--write-golden" in sys.argv:
        new_path = GOLDEN_PATH + ".new"
        with open(new_path, "w", encoding="utf-8") as out:
            json.dump(
                {
                    "fingerprint": fingerprint(),
                    "plans": live_plans,
                },
                out,
                indent=2,
                ensure_ascii=False,
            )
        print(f"Wrote {new_path}. Review the diff, then rename it to {GOLDEN_PATH}.")
        return 0

    print(f"Model plans changed: {len(model_changed)} of {len(plans)}")
    for question, expected, actual in model_changed:
        print(f"- {question}\n    expected: {expected}\n    actual:   {actual}")

    print(f"Live plans changed: {len(live_changed)} of {len(plans)}")
    for question, expected, actual in live_changed:
        print(f"- {question}\n    expected: {expected}\n    actual:   {actual}")

    if unavailable:
        print(f"Could not check (model unavailable): {len(unavailable)}")

    model_unexpected = [
        item for item in model_changed if item[0] not in KNOWN_MODEL_ISSUES
    ]
    return 1 if model_unexpected or live_changed or unavailable else 0


if __name__ == "__main__":
    sys.exit(main())