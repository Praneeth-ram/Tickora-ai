import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.services.model_inference import load_model
from backend.services.answer_writer import write_answer
from backend.services.payroll_narration import (
    build_payroll_facts,
    passes_payroll_answer_check,
)

load_model()

question = "what is my gross amount on august month"
period = {"start_date": "2026-08-01", "end_date": "2026-08-31"}
rows = [{
    "period_start": "2026-08-01", "period_end": "2026-08-31",
    "gross_amount": "84000.00", "deduction_amount": "10080.00",
    "net_amount": "73920.00", "currency": "INR",
}]

payload = build_payroll_facts(question, period, rows)
print("FACTS:", payload)
if payload is None:
    print("RESULT: facts not built, so the LLM is never called")
    sys.exit()

answer = write_answer(question, payload)
print("LLM ANSWER:", repr(answer))
print("CHECK PASSED:", passes_payroll_answer_check(answer, payload))