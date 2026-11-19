import pytest
from types import SimpleNamespace

import backend.services.llm_chat_service as svc
from backend.services import answer_cache, model_inference


def _registry():
    loan = {
        "entity": "loan_request",
        "table": "loan_requests",
        "scope": "employee_manager",
        "fields": ["employee_id", "managed_by_employee_id", "component", "mode", "status", "loan_status"],
        "filters": ["employee_id", "managed_by_employee_id", "component", "mode", "status", "loan_status"],
        "identity_filters": {
            "employee_id": "employee_id",
            "managed_by_employee_id": "employee_id",
        },
        "date_field": "start_month",
        "date_fields": ["start_month"],
        "aggregate_fields": ["total_amount"],
        "group_by_fields": ["status"],
    }
    return {
        f"loan_request.{operation}": {**loan, "operation": operation}
        for operation in ("list", "count", "sum")
    } | {
        "payroll_summary.list": {
            "entity": "payroll_summary",
            "table": "payroll_summaries",
            "operation": "list",
            "fields": ["period_start"],
            "filters": [],
            "identity_filters": {},
            "date_field": "period_start",
            "date_fields": ["period_start"],
        }
    }


def _run(monkeypatch, role, plan, question):
    actor = SimpleNamespace(role=role, employee_id=1, employee_code="EMP001")
    monkeypatch.setattr(svc, "get_actor", lambda: actor)
    monkeypatch.setattr(svc, "get_subject", lambda: None)
    monkeypatch.setattr(svc, "get_query_plan", lambda q: plan)
    registry = _registry()
    monkeypatch.setattr(svc, "build_operation_registry", lambda **kwargs: registry)
    monkeypatch.setattr(svc, "_approved_operations", lambda: frozenset(registry))
    monkeypatch.setattr(model_inference, "fingerprint", lambda: {})
    monkeypatch.setattr(answer_cache, "plan_key", lambda *args: "test-key")
    monkeypatch.setattr(answer_cache, "get_plan", lambda _: None)
    monkeypatch.setattr(answer_cache, "set_plan", lambda *args, **kwargs: None)
    executed = []

    def fake_execute(*args, **kwargs):
        executed.append(args)
        operation_id = args[0]["operation_id"]
        operation = operation_id.rsplit(".", 1)[-1]
        return {
            "data": {"count": 0} if operation == "count" else [],
            "operation": operation,
            "entity": operation_id.split(".", 1)[0],
        }

    monkeypatch.setattr(svc, "execute_query_plan", fake_execute)
    result = svc.run_llm_chat(question, employee_id=1)
    return result, executed


def test_employee_payroll_is_refused_and_not_executed(monkeypatch):
    result, executed = _run(
        monkeypatch, "employee",
        {"operation_id": "payroll_summary.list", "filters": {}},
        "What is my salary this month?",
    )
    assert result["intent"] == "access_denied"
    assert executed == []


@pytest.mark.parametrize("role", ["employee", "admin"])
@pytest.mark.parametrize(
    "question",
    ["Show my loans", "Show all loan requests in the organization"],
)
def test_non_super_admin_loan_queries_are_limited_to_own_records(
    monkeypatch, role, question
):
    result, executed = _run(
        monkeypatch,
        role,
        {"operation_id": "loan_request.list", "filters": {}},
        question,
    )
    assert result["intent"] == "loan_lookup"
    assert executed
    final_plan = executed[-1][0]
    assert final_plan["scope"] == "own"
    assert final_plan["filters"]["employee_id"] == {"$context": "employee_id"}

def test_graph_correction_blocks_restricted_role_before_queries(monkeypatch):
    from backend.agents import nodes

    actor = SimpleNamespace(role="employee", employee_id=1, employee_code="EMP001")
    monkeypatch.setattr(nodes, "get_actor", lambda: actor)

    def forbidden(*args, **kwargs):
        raise AssertionError("correction ran for a restricted role")

    monkeypatch.setattr(nodes, "correct_plan", forbidden)
    state = {
        "question": "What is my salary this month?",
        "normalized_question": "What is my salary this month?",
        "raw_plan": {"operation_id": "payroll_summary.list", "filters": {}},
        "employee_id": 1,
        "organization_id": 1,
    }
    out = nodes.correction_node(state)
    assert out["status"] == "access_denied"