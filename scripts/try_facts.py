import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.agents.graph import get_chat_graph
from backend.security.access_policy import Actor, SUPER_ADMIN, set_actor, reset_actor
from backend.services.model_inference import load_model

load_model()

actor = Actor(employee_id=1, organization_id=1, department_id=None,
              role=SUPER_ADMIN, employee_code="EMP001")
token = set_actor(actor)
try:
    graph = get_chat_graph()
    for q in ["Count my present days in October 2026.",
              "How many leave requests per status?"]:
        out = graph.invoke({"session_id": "facts", "employee_id": 1,
                            "employee_code": "EMP001", "organization_id": 1,
                            "question": q})
        print("Q:", q, "| A:", out["result"].get("answer"))
finally:
    reset_actor(token)