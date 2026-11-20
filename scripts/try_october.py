import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.agents.graph import get_chat_graph
from backend.security.access_policy import Actor, SUPER_ADMIN, set_actor, reset_actor
from backend.services.model_inference import load_model

EMP001_ID = 1  # replace with EMP001's id from the employees table

load_model()

QUESTIONS = [
    "How many days was I absent in October?",
    "How many days was I present in October?",
    "How many hours did I work in October?",
    "Show my attendance breakdown for October.",
]

actor = Actor(
    employee_id=EMP001_ID,
    organization_id=1,  # replace with the real organization id
    department_id=None,
    role=SUPER_ADMIN,
    employee_code="EMP001",
)

token = set_actor(actor)
try:
    graph = get_chat_graph()
    for question in QUESTIONS:
        out = graph.invoke({
            "session_id": "october-test",
            "employee_id": actor.employee_id,
            "employee_code": actor.employee_code,
            "organization_id": actor.organization_id,
            "question": question,
        })
        result = out["result"]
        print("Q:", question)
        print("A:", result.get("answer"))
        print("intent:", result.get("intent"), "| show_table:", result.get("show_table"))
        print("-" * 60)
finally:
    reset_actor(token)