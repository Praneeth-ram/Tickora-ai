"""Run real chat questions through the graph and check narration for every entity.

Every figure comes from the database, so this measures narration on real data.
Set the flag in the shell (LLM_NARRATION_ENABLED=True) before running.

Route per question:
  llm        the LLM answer was accepted by passes_answer_check
  fallback   the LLM answer was rejected, so the template answer is shown
  template   no LLM answer was attempted (table route, sensitive entity, etc.)

Status per question:
  PASS    llm answer, or template for a sensitive entity
  REVIEW  template or fallback for a narratable entity (check whether expected)
  FAIL    LLM answer for a sensitive entity, an empty answer, or a graph error
"""
import json
import logging
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.agents.graph import get_chat_graph
from backend.security.access_policy import Actor, SUPER_ADMIN, set_actor, reset_actor
from backend.services.model_inference import load_model

EMP_ID = 1          # EMP001
ORG_ID = 1          # real organization id
SENSITIVE_ENTITIES = {"loan_request", "payroll_summary"}

# Questions grouped by entity. The key is the entity name used by the registry.
QUESTIONS_BY_ENTITY = {
    "attendance": [
        # Count (present, absent, late, half day)
        "How many days was I present in October?",
        "How many days was I absent in October?",
        "How many days was I late in October?",
        "How many half days did I take in October?",
        "How many days was I present in September?",
        "How many days was I absent in September?",
        "How many days was I late in September?",
        "Count my present days in October 2026.",
        "How many late days did I have this month?",
        "How many absences did I have in October?",
        # Sum (hours and overtime)
        "How many hours did I work in October?",
        "What is my total worked time in September?",
        "How much overtime did I do in October?",
        "Total overtime in September?",
        "How many hours did I work in October 2026?",
        # Breakdown (group by status)
        "Show my attendance breakdown for October.",
        "Give me my attendance summary for September.",
        "Attendance overview for October.",
        "How many days per status in October?",
        "What is my attendance status breakdown for September?",
    ],
    "attendance_punch": [
        "How many clock punches did I have in October 2026?",
        "Show my clock punches for 2 October 2026.",
    ],
    "attendance_adjustment": [
        "How many attendance adjustments did I make in October 2026?",
    ],
    "leave_request": [
        "How many leave requests did I have in October 2026?",
        "Show my leave requests for October 2026.",
        "How many leave requests per status in 2026?",
    ],
    "leave_balance": [
        "What is my leave balance for 2026?",
        "How many leave days do I have left this year?",
        "How many leave days did I use in 2026?",
    ],
    "leave_type": [
        "What leave types are available?",
        "How many leave types are there?",
    ],
    "wfh_request": [
        "How many work from home requests did I make in October 2026?",
        "Show my work from home requests for September 2026.",
    ],
    "timesheet": [
        "How many timesheets did I submit in October 2026?",
        "Show my timesheets for September 2026.",
    ],
    "holiday": [
        "How many holidays are there in October 2026?",
        "List the holidays in November 2026.",
    ],
    "task": [
        "How many tasks did I have in October 2026?",
        "How many tasks per status in October 2026?",
        "What is my total performance score in September 2026?",
    ],
    "work_schedule": [
        "What is my work schedule?",
        "Show my work schedule.",
    ],
    "loan_request": [
        "How many loans do I have?",
        "What is my remaining loan amount?",
    ],
    "payroll_summary": [
        "What was my net pay in September 2026?",
        "How many payslips do I have in 2026?",
    ],
}

EVAL_QUESTIONS = [
    (entity, question)
    for entity, questions in QUESTIONS_BY_ENTITY.items()
    for question in questions
]

SUSPICIOUS_RE = re.compile(r"[{}\[\]]|\bnull\b|\bNone\b|\bundefined\b", re.IGNORECASE)


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def _route(messages: list[str]) -> str:
    if any(m.startswith("Payroll narration accepted") for m in messages):
        return "llm"
    if any(m.startswith("Payroll narration rejected") for m in messages):
        return "fallback"
    if any(m.startswith("answer rejected") for m in messages):
        return "fallback"
    if any(m.startswith("Facts not built") for m in messages):
        return "no_facts"
    if any(m.startswith("facts:") for m in messages):
        return "llm"
    if any(m.startswith("Narration skipped") for m in messages):
        return "gate"
    if any(m.startswith("Narration gate") for m in messages):
        return "no_facts"
    if any(m.startswith("Payroll facts not built") for m in messages):
        return "no_facts"
    return "template"


def _rejected_text(messages: list[str]) -> str | None:
    for m in messages:
        if m.startswith("answer rejected") or m.startswith("Payroll narration rejected"):
            return m
    return None

def _status(entity: str, route: str, answer: str) -> str:
    if not answer or SUSPICIOUS_RE.search(answer):
        return "FAIL"
    if entity in SENSITIVE_ENTITIES:
        return "FAIL" if route == "llm" else "PASS"
    return "PASS" if route == "llm" else "REVIEW"


def main() -> None:
    load_model()
    capture = _Capture()
    logging.getLogger("backend.agents.nodes").addHandler(capture)

    actor = Actor(employee_id=EMP_ID, organization_id=ORG_ID, department_id=None,
                  role=SUPER_ADMIN, employee_code="EMP001")
    token = set_actor(actor)
    rows = []
    try:
        graph = get_chat_graph()
        for entity, question in EVAL_QUESTIONS:
            capture.messages.clear()
            try:
                out = graph.invoke({
                    "session_id": "eval", "employee_id": EMP_ID,
                    "employee_code": "EMP001", "organization_id": ORG_ID,
                    "question": question,
                })
                answer = out["result"].get("answer") or ""
                intent = out["result"].get("intent")
                error = None
            except Exception as exc:  # keep going; record the failure
                answer, intent, error = "", None, repr(exc)
            route = "error" if error else _route(capture.messages)
            status = "FAIL" if error else _status(entity, route, answer)
            rejected = _rejected_text(capture.messages)
            rows.append({
                "entity": entity, "question": question, "answer": answer,
                "intent": intent, "route": route, "status": status,
                "error": error, "rejected": rejected,
            })
    finally:
        reset_actor(token)
        logging.getLogger("backend.agents.nodes").removeHandler(capture)

    out_path = ROOT / "tests" / "fixtures" / "narration_eval.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")

    for r in rows:
        print(f"[{r['status']}] {r['entity']} | route={r['route']}")
        print("Q:", r["question"])
        print("A:", r["answer"] or r["error"])
        if r.get("rejected"):
            print("REJECTED:", r["rejected"])
        print("-" * 60)

    print("\nSUMMARY")
    print("Status:", dict(Counter(r["status"] for r in rows)))
    by_entity: dict[str, Counter] = {}
    for r in rows:
        by_entity.setdefault(r["entity"], Counter())[r["status"]] += 1
    for entity, counts in by_entity.items():
        print(f"  {entity:24s} PASS={counts['PASS']:<3d} REVIEW={counts['REVIEW']:<3d} FAIL={counts['FAIL']}")
    print(f"\nFull results: {out_path}")


if __name__ == "__main__":
    main()