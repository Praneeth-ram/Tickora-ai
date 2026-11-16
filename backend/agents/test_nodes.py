from datetime import date

import pytest

from backend.agents import nodes
from backend.agents.graph import get_chat_graph
from backend.services import chat_memory


@pytest.mark.parametrize(
    "last_operation",
    [
        "attendance.list",
        "leave_request.list",
        "wfh_request.list",
        "timesheet.list",
        "holiday.list",
        "task.list",
        "loan_request.list",
        "payroll_summary.list",
    ],
)
def test_period_only_follow_up_reuses_the_previous_operation(
    monkeypatch, last_operation
):
    question = "in 2026?"
    state = {
        "question": question,
        "last_operation": last_operation,
        "employee_id": 11,
        "organization_id": 1,
    }

    assert nodes.supervisor_node(state) == {"request_type": "query"}
    monkeypatch.setattr(nodes, "direct_answer", lambda *args: None)

    context = nodes.context_node(state)

    assert context["raw_plan"] == {
        "operation_id": last_operation,
        "filters": {},
    }


@pytest.mark.parametrize(
    ("question", "year"),
    [("in 2025?", 2025), ("in 2026?", 2026)],
)
def test_period_only_follow_up_applies_year_to_previous_operation(
    monkeypatch, question, year
):
    state = {
        "question": question,
        "last_operation": "leave_request.list",
        "employee_id": 11,
        "organization_id": 1,
    }
    monkeypatch.setattr(nodes, "direct_answer", lambda *args: None)
    monkeypatch.setattr(nodes, "get_current_date", lambda: date(2026, 11, 16))

    state.update(nodes.context_node(state))
    correction = nodes.correction_node(state)

    assert correction["plan"]["operation_id"] == "leave_request.list"
    assert correction["plan"]["filters"]["start_date"] == {
        "gte": f"{year}-01-01",
        "lte": f"{year}-12-31",
    }


def test_unrelated_question_does_not_inherit_the_previous_operation():
    assert nodes.supervisor_node({
        "question": "is 2026 a leap year?",
        "last_operation": "leave_request.list",
    }) == {"request_type": "out_of_scope"}


def test_invalid_date_is_reported_by_chat_graph(monkeypatch):
    monkeypatch.setattr(chat_memory, "load_last_topic", lambda *args: None)
    monkeypatch.setattr(
        nodes,
        "plan_question",
        lambda _question: {"operation_id": "attendance.list", "filters": {}},
    )
    monkeypatch.setattr(nodes, "is_approved_operation", lambda _operation_id: True)

    graph_result = get_chat_graph().invoke(
        {
            "question": "32 October 2026 attendance",
            "session_id": "invalid-date-test",
            "employee_id": 11,
            "employee_code": "EMP011",
            "organization_id": 1,
        }
    )

    assert "not a valid date" in graph_result["result"]["answer"]
    assert graph_result["result"]["intent"] == "attendance_records"
