import pytest

from backend.security.access_policy import ADMIN, EMPLOYEE, SUPER_ADMIN, Actor, AccessDenied
from backend.services.dynamic_query_service import execute_team_summary
from backend.services.llm_chat_service import is_team_question


@pytest.mark.parametrize("question, expected", [
    ("Show my team's attendance for October", True),
    ("Show attendance for everyone in my department", True),
    ("Show all employees' attendance", True),
    ("Is October 31 a company holiday?", False),
    ("Is there a team holiday on October 31?", False),
    ("What are my attendance records for October?", False),
])
def test_team_question_detection(question, expected):
    assert is_team_question(question) is expected


def test_employee_cannot_run_team_summary():
    actor = Actor(employee_id=1, organization_id=1, department_id=2, role=EMPLOYEE)
    with pytest.raises(AccessDenied):
        execute_team_summary(actor=actor, start=None, end=None, db_engine=None)