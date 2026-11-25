"""Item 8: model and pipeline failures produce controlled chat responses, not 500s."""
from types import SimpleNamespace

import pytest

from backend.services.context_window import ContextWindowExceededError
from backend.services.model_errors import ModelServiceError, ModelUnavailableError

from .conftest import EMP011, requires_db


def test_context_window_error_is_a_model_error_and_still_a_value_error():
    error = ContextWindowExceededError("too big")
    assert isinstance(error, ModelServiceError)
    assert isinstance(error, ValueError)


@requires_db
def test_oversized_prompt_at_planning_falls_back_instead_of_raising(monkeypatch):
    from backend.services import llm_chat_service

    def too_big(_question):
        raise ContextWindowExceededError("prompt too large")

    monkeypatch.setattr(llm_chat_service, "get_query_plan", too_big)
    plan = llm_chat_service.plan_question("show my attendance")
    assert llm_chat_service.is_approved_operation(plan.get("operation_id"))


def _call_chat(monkeypatch, as_actor, error):
    from backend import main

    as_actor(*EMP011)  # _chat is fail-closed without a verified actor

    class _Graph:
        def invoke(self, _state):
            raise error

    monkeypatch.setattr("backend.agents.graph.get_chat_graph", lambda: _Graph())
    monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(agent_orchestration=True))
    body = main.ChatRequest(question="Show my attendance for October 2026", session_id="fallback-test")
    return main._chat(body, 11, {"employee_code": "EMP011", "organization_id": 1})


@requires_db
def test_model_failure_in_the_graph_returns_a_chat_message(monkeypatch, as_actor):
    result = _call_chat(monkeypatch, as_actor, ModelUnavailableError("model down"))
    assert result["intent"] == "unavailable"
    assert "temporarily unavailable" in result["answer"]


@requires_db
def test_unexpected_failure_in_the_graph_returns_a_chat_message_and_no_details(monkeypatch, as_actor):
    result = _call_chat(monkeypatch, as_actor, KeyError("internal_detail_xyz"))
    assert result["intent"] == "unsupported"
    assert "internal_detail_xyz" not in str(result)
    assert "Something went wrong" in result["answer"]


@requires_db
def test_deliberate_http_errors_are_not_swallowed(monkeypatch, as_actor):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as caught:
        _call_chat(monkeypatch, as_actor, HTTPException(status_code=418, detail="teapot"))
    assert caught.value.status_code == 418  # ours, not the 403 from the auth check