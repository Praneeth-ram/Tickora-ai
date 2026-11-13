import json
import sys
from datetime import date
from pathlib import Path

from backend.services.llm_chat_service import (
    normalize_and_correct_plan,
    plan_question,
)
from backend.services.model_inference import fingerprint, load_model

OUT = Path("tests/fixtures/golden_plans.json")
GATE_TODAY = date(2026, 11, 11)

QUESTIONS = [
    "What are my attendance records for October?",
    "Is October 31 a holiday?",
    "Show my leave requests",
    "Show my WFH requests",
    "Show my timesheets for October",
    "What is my gross salary?",
    "Show my loan requests",
    "How many leave requests do I have?",
    "Show my assigned tasks",
    "How many holidays are there in 2026?",
    "Show my leave balance",
    "What was my clock-in time on October 5?",
]

def main() -> int:
    load_model()
    plans = {}
    for question in QUESTIONS:
        raw = plan_question(question)
        plans[question], _period = normalize_and_correct_plan(
            raw, question, GATE_TODAY
        )

    golden = {
        "fingerprint": fingerprint(),
        "plans": plans,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(golden, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {len(golden['plans'])} plans to {OUT}")
    return 0

if __name__ == "__main__":
    sys.exit(main())