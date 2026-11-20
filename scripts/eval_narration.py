"""Run real chat questions through the graph and record narration outcomes.

Every figure comes from the database, so this measures narration on real data.
Set the flag in the shell (LLM_NARRATION_ENABLED=True) before running.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.agents.graph import get_chat_graph
from backend.security.access_policy import Actor, SUPER_ADMIN, set_actor, reset_actor
from backend.services.model_inference import load_model

EMP_ID = 1          # EMP001
ORG_ID = 1          # real organization id
QUESTIONS = [
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
    "How many leave requests per status?",
]

load_model()
actor = Actor(employee_id=EMP_ID, organization_id=ORG_ID, department_id=None,
              role=SUPER_ADMIN, employee_code="EMP001")
token = set_actor(actor)
rows = []
try:
    graph = get_chat_graph()
    for q in QUESTIONS:
        out = graph.invoke({
            "session_id": "eval", "employee_id": EMP_ID,
            "employee_code": "EMP001", "organization_id": ORG_ID, "question": q,
        })
        rows.append({"question": q, "answer": out["result"].get("answer"),
                     "intent": out["result"].get("intent")})
finally:
    reset_actor(token)

Path("tests/fixtures").mkdir(parents=True, exist_ok=True)
Path("tests/fixtures/narration_eval.json").write_text(
    json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
for r in rows:
    print("Q:", r["question"]); print("A:", r["answer"]); print("-" * 60)