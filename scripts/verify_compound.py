import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.services.model_inference import load_model
from backend.agents.graph import get_chat_graph
from backend.security.access_policy import Actor, SUPER_ADMIN, set_actor, reset_actor
from backend.config import get_settings

PAIRS = [
    "Show my leave in October and attendance in September",
    "Show my attendance in September and leave in October",
    "Show my attendance in September and attendance in October",
    "Show my leave in October and holidays in November",
]

load_model()
actor = Actor(employee_id=1, organization_id=1, department_id=None,
              role=SUPER_ADMIN, employee_code="EMP001")
token = set_actor(actor)
try:
    graph = get_chat_graph()
    base = {"session_id": "verify", "employee_id": 1,
            "employee_code": "EMP001", "organization_id": 1}
    for question in PAIRS:
        out = graph.invoke({**base, "question": question})["result"]
        print("Q:", question)
        print("period:", out["period"])
        print("A:", out["answer"])
        print("-" * 60)
finally:
    reset_actor(token)