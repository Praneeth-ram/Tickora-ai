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
import os
os.environ.setdefault("NARRATION_DEBUG_LOGGING", "True")  # the eval needs the detailed lines

from backend.config import Settings
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

# Questions that ask for a list or table are allowed to stay as templates.
LIST_RE = re.compile(r"^(?:show|list)\b|\bavailable\b|\bwork schedule\b", re.IGNORECASE)
MISS_PREFIXES = (
    "I couldn't answer",
    "I couldn't provide",
    "I can answer questions about",
)
SUSPICIOUS_RE = re.compile(r"[{}\[\]]|\bnull\b|\bNone\b|\bundefined\b", re.IGNORECASE)
TRACE_PREFIXES = (
    "Narration", "Payroll", "Facts not built", "answer rejected", "facts:",
    "verifier compare",
)


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def _route(messages: list[str]) -> str:
    entry = next((m for m in messages if m.startswith("Narration entry")), None)
    if any(m.startswith("Payroll narration accepted") for m in messages):
        return "llm"
    if any(m.startswith("Payroll narration rejected") for m in messages):
        return "fallback"
    if any(m.startswith("answer rejected") for m in messages):
        return "fallback"
    if any(m.startswith("facts:") for m in messages):
        return "llm"
    if any(m.startswith("Narration skipped") for m in messages):
        return "gate"
    if any(m.startswith(("Narration gate", "Facts not built", "Payroll facts not built"))
           for m in messages):
        return "no_facts"
    if entry is not None and "choose_route=table" in entry:
        return "table"
    if entry is None:
        return "bypassed"  # answered by a builder before _route_answer ran
    return "template"


def _trace(messages: list[str]) -> str:
    lines = [m[:300] for m in messages if m.startswith(TRACE_PREFIXES)]
    return " | ".join(lines)


def _verifier_reasons(line: str) -> tuple[str | None, str | None]:
    match = re.search(r"\bold=(.*?)\s+new=(.*?)\s+answer=", line)
    if not match:
        return None, None
    old = match.group(1).strip()
    new = match.group(2).strip()
    return (None if old == "None" else old, None if new == "None" else new)


def _status(entity: str, route: str, answer: str, row_count: int) -> str:
    if not answer or SUSPICIOUS_RE.search(answer):
        return "FAIL"
    if answer.startswith(MISS_PREFIXES):
        return "MISS"
    if entity == "loan_request":
        return "PASS" if route == "gate" else "FAIL"
    if route == "llm":
        return "PASS"
    if route == "table":
        return "PASS" if row_count > 5 else "REVIEW"
    return "REVIEW"


def main() -> None:
    if not Settings().llm_narration_enabled:
        print("ABORT: LLM_NARRATION_ENABLED is False. Set it to True and run again.")
        return

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
            except Exception as exc:
                answer, intent, error = "", None, repr(exc)
            route = "error" if error else _route(capture.messages)
            row_count = len(out["result"].get("data") or []) if not error else 0
            status = "FAIL" if error else _status(entity, route, answer, row_count)
            if entity == "loan_request" and route == "llm":
                status = "FAIL"  # loan is sensitive and must stay template
            rows.append({
                "entity": entity, "question": question, "answer": answer,
                "intent": intent, "route": route, "status": status,
                "error": error,
                "rejected": next((m for m in capture.messages
                                  if m.startswith(("answer rejected",
                                                   "Payroll narration rejected"))), None),
                "trace": None if route == "llm" else _trace(capture.messages),
                "verifier": next((m for m in capture.messages if m.startswith("verifier compare")), None),
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
        if r["rejected"]:
            print("REJECTED:", r["rejected"])
        if r.get("verifier"):
            print("VERIFY:", r["verifier"])
        if r["trace"]:
            print("TRACE:", r["trace"])
        print("-" * 60)

    print("\nSUMMARY")
    print("Status:", dict(Counter(r["status"] for r in rows)))
    print("Routes:", dict(Counter(r["route"] for r in rows)))
    by_entity: dict[str, Counter] = {}
    routes_by_entity: dict[str, Counter] = {}
    for r in rows:
        by_entity.setdefault(r["entity"], Counter())[r["status"]] += 1
        routes_by_entity.setdefault(r["entity"], Counter())[r["route"]] += 1
    for entity in by_entity:
        c = by_entity[entity]
        print(f"  {entity:24s} PASS={c['PASS']:<3d} REVIEW={c['REVIEW']:<3d} "
              f"MISS={c['MISS']:<3d} FAIL={c['FAIL']:<3d} "
              f"routes={dict(routes_by_entity[entity])}")

    comparison_counts = {
        "pass/pass": 0,
        "pass/fail": 0,
        "fail/pass": 0,
        "fail/fail": 0,
    }
    verifier_lines = []
    for r in rows:
        verifier = r.get("verifier")
        if not verifier:
            continue
        old_reason, new_reason = _verifier_reasons(verifier)
        group = (
            ("pass" if old_reason is None else "fail")
            + "/"
            + ("pass" if new_reason is None else "fail")
        )
        comparison_counts[group] += 1
        verifier_lines.append(
            f"{group} | {r['entity']} | Q: {r['question']} | A: {r['answer']}"
        )

    print("\nVERIFIER COMPARISON")
    for group in ("pass/pass", "pass/fail", "fail/pass", "fail/fail"):
        print(f"{group}: {comparison_counts[group]}")

    verifier_path = ROOT / "tests" / "fixtures" / "verifier_compare.txt"
    verifier_path.parent.mkdir(parents=True, exist_ok=True)
    verifier_path.write_text(
        "\n".join(verifier_lines) + ("\n" if verifier_lines else ""),
        encoding="utf-8",
    )

    print(f"\nFull results: {out_path}")


if __name__ == "__main__":
    main()