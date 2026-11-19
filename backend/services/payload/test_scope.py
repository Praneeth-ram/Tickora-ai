from datetime import date
from types import SimpleNamespace

import backend.services.llm_chat_service as svc
from backend.services import answer_cache, model_inference
from backend.services.llm_chat_service import is_team_question, query_scope


SUPER = SimpleNamespace(role="super_admin")
EMPLOYEE = SimpleNamespace(role="employee")
ADMIN = SimpleNamespace(role="admin")


def test_super_admin_own_question_is_own():
    assert query_scope("Show my loans", SUPER) == "own"
    assert query_scope("What is my salary this month?", SUPER) == "own"
    assert query_scope("How many loan requests do I have?", SUPER) == "own"


def test_super_admin_organization_question_is_org():
    assert query_scope("Show all loan requests in the organization", SUPER) == "org"
    assert query_scope("How many loan requests does everyone have?", SUPER) == "org"
    assert query_scope("How many loan requests are in the organization?", SUPER) == "org"


def test_super_admin_default_without_wording_is_own():
    assert query_scope("How many loan requests are pending?", SUPER) == "own"


def test_employee_and_admin_are_always_own():
    assert query_scope("Show all loan requests in the organization", EMPLOYEE) == "own"
    assert query_scope("Show all loan requests in the organization", ADMIN) == "own"


def test_organization_scope_alone_does_not_trigger_team_attendance():
    assert not is_team_question("How many loan requests are in the organization?")
    assert is_team_question("How many team members were present?")


def test_loan_plan_scope_overrides_a_conflicting_model_operation(monkeypatch):
    loan_definition = {
        "entity": "loan_request",
        "table": "loan_requests",
        "fields": ["employee_id", "managed_by_employee_id", "component", "mode", "status", "loan_status"],
        "identity_filters": {
            "employee_id": "employee_id",
            "managed_by_employee_id": "employee_id",
        },
        "date_field": "start_month",
        "group_by_fields": ["status"],
        "aggregate_fields": ["total_amount"],
    }
    registry = {
        f"loan_request.{operation}": {**loan_definition, "operation": operation}
        for operation in ("list", "count", "sum")
    }
    monkeypatch.setattr(svc, "get_actor", lambda: SUPER)
    monkeypatch.setattr(svc, "build_operation_registry", lambda: registry)

    own_plan, _ = svc.normalize_and_correct_plan(
        {"operation_id": "attendance.list", "filters": {}},
        "How many loan requests do I have?",
        date(2026, 11, 19),
    )
    org_plan, _ = svc.normalize_and_correct_plan(
        {"operation_id": "attendance.list", "filters": {}},
        "How many loan requests are in the organization?",
        date(2026, 11, 19),
    )

    assert own_plan["operation_id"] == "loan_request.count"
    assert own_plan["scope"] == "own"
    assert org_plan["operation_id"] == "loan_request.count"
    assert org_plan["scope"] == "org"


def test_plan_question_uses_explicit_entity_before_validating_model_plan(monkeypatch):
    loan_definition = {
        "entity": "loan_request",
        "table": "loan_requests",
        "operation": "count",
        "fields": [],
        "filters": [],
    }
    registry = {"loan_request.count": loan_definition}
    question = "How many loan requests are in the organization?"

    monkeypatch.setattr(svc, "get_actor", lambda: SUPER)
    monkeypatch.setattr(svc, "build_operation_registry", lambda **kwargs: registry)
    monkeypatch.setattr(svc, "get_query_plan", lambda _: {
        "operation_id": "attendance.list",
        "filters": {},
    })
    monkeypatch.setattr(svc, "is_approved_operation", lambda operation: operation in registry)
    monkeypatch.setattr(model_inference, "fingerprint", lambda: {})
    monkeypatch.setattr(answer_cache, "plan_key", lambda *args: "test-key")
    monkeypatch.setattr(answer_cache, "get_plan", lambda _: None)
    monkeypatch.setattr(answer_cache, "set_plan", lambda *args, **kwargs: None)

    plan = svc.plan_question(question)

    assert plan["operation_id"] == "loan_request.count"


def test_loan_count_response_uses_the_resolved_scope(monkeypatch):
    monkeypatch.setattr(svc, "get_actor", lambda: SUPER)

    assert svc.count_response("loan_request", 2, None, "", scope="own") == (
        "You have 2 loan requests."
    )
    assert svc.count_response("loan_request", 2, None, "", scope="org") == (
        "There are 2 loan requests in your organization."
    )