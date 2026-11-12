from unittest.mock import patch
import pytest
from backend.security.access_policy import (
    REFUSAL_MESSAGE,
    AccessDenied,
    Actor,
    EMPLOYEE,
    set_actor,
    reset_actor,
)
from backend.services import llm_chat_service
from backend.services.dynamic_query_service import execute_query_plan
from backend.agents import nodes


@pytest.fixture
def emp002_actor():
    """Admin in department 2, organization 1 (matches the test data)."""
    token = set_actor(Actor(2, 1, 2, "admin"))
    yield
    reset_actor(token)


def test_run_llm_chat_returns_refusal_when_access_denied(emp002_actor):
    with patch.object(
        llm_chat_service,
        "execute_and_format",
        side_effect=AccessDenied(),
    ):
        result = llm_chat_service.run_llm_chat(
            "Show Arjun Kumar's attendance for October.",
            employee_id=2,
            organization_id=1,
        )

    assert result["answer"] == REFUSAL_MESSAGE
    assert result["intent"] == "access_denied"
    assert result["success"] is True


def test_execution_node_returns_refusal_when_access_denied():
    state = {
        "question": "Show Arjun Kumar's attendance for October.",
        "normalized_question": "Show Arjun Kumar's attendance for October.",
        "plan": {"operation_id": "attendance.list", "filters": {}},
        "period": {"start_date": "2026-10-01", "end_date": "2026-10-31"},
        "employee_id": 2,
        "organization_id": 1,
    }
    with patch.object(
        nodes,
        "execute_and_format",
        side_effect=AccessDenied(),
    ):
        out = nodes.execution_node(state)

    assert out["result"]["answer"] == REFUSAL_MESSAGE
    assert out["result"]["intent"] == "access_denied"


def test_execute_query_plan_fails_closed_without_actor():
    # No actor set in context: the query must not run.
    plan = {"operation_id": "attendance.list", "filters": {}}
    with pytest.raises(AccessDenied):
        execute_query_plan(plan, employee_id=11, organization_id=1, db_engine=None)