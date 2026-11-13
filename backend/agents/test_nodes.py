from backend.agents import nodes
from backend.agents.graph import get_chat_graph
from backend.services import chat_memory


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
