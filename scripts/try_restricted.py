import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.agents.graph import get_chat_graph
from backend.security.access_policy import ADMIN, SUPER_ADMIN, Actor, EMPLOYEE, set_actor, reset_actor
from backend.services.model_inference import load_model

load_model()

# An ordinary employee, not a super admin. Replace with a real employee id
# and organization id if they differ.
actor = Actor(
    employee_id=11,
    organization_id=1,
    department_id=None,
    role=EMPLOYEE,
    employee_code="EMP011",
)

QUESTIONS = [
    "What is my salary this month?",
    "Show my loans",
    "How many loan requests are in the organization?",
]

token = set_actor(actor)
try:
    graph = get_chat_graph()
    for question in QUESTIONS:
        out = graph.invoke({
            "session_id": "restricted-test",
            "employee_id": actor.employee_id,
            "employee_code": actor.employee_code,
            "organization_id": actor.organization_id,
            "question": question,
        })
        result = out["result"]
        print("Q:", question)
        print("A:", result.get("answer"))
        print("intent:", result.get("intent"))
        print("-" * 60)
finally:
    reset_actor(token)