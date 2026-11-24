import sys, traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.agents.graph import get_chat_graph
from backend.services.model_inference import load_model
from backend.security.access_policy import Actor, SUPER_ADMIN, set_actor

load_model()
set_actor(Actor(employee_id=1, organization_id=1, department_id=None,
                role=SUPER_ADMIN, employee_code="EMP001"))
graph = get_chat_graph()
try:
    graph.invoke({"session_id": "dbg", "employee_id": 1, "employee_code": "EMP001",
                  "organization_id": 1, "question": "How many loans do I have?"})
    print("no exception")
except Exception:
    traceback.print_exc()