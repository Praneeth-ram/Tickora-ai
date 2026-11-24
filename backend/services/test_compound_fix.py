"""Tests for compound-question LLM narration fixes."""

from __future__ import annotations
from unittest.mock import MagicMock, patch
import pytest

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

LEAVE_FACTS = {
    "entity": "leave request", "count": 0, "found": False,
    "period_text": "October 2026",
    "unit": "leave requests", "unit_singular": "leave request",
}
ATT_FACTS = {
    "entity": "attendance", "count": 22, "found": True,
    "period_text": "September 2026",
    "unit": "days", "unit_singular": "day",
    "groups": [
        {"label": "present", "count": 18},
        {"label": "late",    "count": 3},
        {"label": "absent",  "count": 1},
    ],
}
HOLIDAY_FACTS = {
    "entity": "holiday", "count": 0, "found": False,
    "period_text": "November 2026",
    "unit": "holidays", "unit_singular": "holiday",
}
ATT_SEP = {
    "entity": "attendance", "count": 22, "found": True,
    "period_text": "September 2026", "unit": "days", "unit_singular": "day",
}
ATT_OCT = {
    "entity": "attendance", "count": 16, "found": True,
    "period_text": "October 2026", "unit": "days", "unit_singular": "day",
}


def _merged(parts):
    return {
        "compound": True,
        "period_text": "September 2026 to November 2026",
        "parts": [{"order": i + 1, **p} for i, p in enumerate(parts)],
    }


# ---------------------------------------------------------------------------
# 1.  _route_answer: facts must not be overwritten with None
# ---------------------------------------------------------------------------

def test_route_answer_sets_facts_when_narratable(monkeypatch):
    from backend.agents import nodes

    good_facts = {"entity": "attendance", "count": 22, "found": True}

    monkeypatch.setattr(nodes, "get_actor", lambda: MagicMock(role="employee"))
    monkeypatch.setattr(nodes, "_entity_specs", lambda: {"attendance": {"narratable": True, "sensitive": False}})
    monkeypatch.setattr(nodes, "narratable_for_role", lambda *_: True)
    monkeypatch.setattr(nodes, "compute_facts", lambda *_, **__: good_facts)
    monkeypatch.setattr(nodes, "choose_route", lambda *_: "llm")
    monkeypatch.setattr(nodes, "get_subject", lambda: None)
    monkeypatch.setattr(nodes.settings, "llm_narration_enabled", False)

    result = {
        "intent": "attendance_records",
        "answer": "template", "message": "template",
        "data": [{"status": "PRESENT"}] * 22,
    }
    out = nodes._route_answer(
        "Show my September attendance",
        result,
        {"operation_id": "attendance.list", "filters": {}},
        {"start_date": "2026-09-01", "end_date": "2026-09-30"},
    )
    assert out["facts"] == good_facts


def test_route_answer_does_not_set_facts_when_not_narratable(monkeypatch):
    from backend.agents import nodes

    monkeypatch.setattr(nodes, "get_actor", lambda: MagicMock(role="employee"))
    monkeypatch.setattr(nodes, "_entity_specs", lambda: {"attendance": {"narratable": False, "sensitive": False}})
    monkeypatch.setattr(nodes, "narratable_for_role", lambda *_: False)
    monkeypatch.setattr(nodes, "compute_facts", lambda *_, **__: {"entity": "attendance"})
    monkeypatch.setattr(nodes, "choose_route", lambda *_: "llm")
    monkeypatch.setattr(nodes, "get_subject", lambda: None)
    monkeypatch.setattr(nodes.settings, "llm_narration_enabled", False)

    result = {
        "intent": "attendance_records",
        "answer": "template", "message": "template",
        "data": [],
    }
    out = nodes._route_answer(
        "Show my September attendance",
        result,
        {"operation_id": "attendance.list", "filters": {}},
        {"start_date": "2026-09-01", "end_date": "2026-09-30"},
    )
    assert out.get("facts") is None


# ---------------------------------------------------------------------------
# 2.  compound_node: graceful fallback when parts lack facts
# ---------------------------------------------------------------------------

def _sub(intent, answer, facts=None):
    r = {
        "intent": intent, "answer": answer, "message": answer,
        "success": True,
        "period": {"start_date": "2026-09-01", "end_date": "2026-10-31"},
        "show_table": False, "data": [], "raw_data": [],
    }
    if facts is not None:
        r["facts"] = facts
    return r


@pytest.fixture()
def state():
    return {
        "session_id": "test", "employee_id": 1,
        "employee_code": "EMP001", "organization_id": 1,
        "question": "Show my leave in October and attendance in September",
    }


def test_compound_node_falls_back_when_facts_missing(monkeypatch, state):
    from backend.agents import nodes

    sub1 = _sub("leave_status",      "You have no leave in October.")
    sub2 = _sub("attendance_records", "You have 22 records in September.")

    mock_graph = MagicMock()
    mock_graph.invoke.side_effect = lambda s: {
        "result": sub1 if "leave" in s["question"].lower() else sub2
    }

    monkeypatch.setattr(nodes, "split_compound_question", lambda _: [
        "Show my leave in October",
        "Show my attendance in September",
    ])
    monkeypatch.setattr(nodes.settings, "llm_narration_enabled", True)

    with patch("backend.agents.nodes.get_chat_graph", return_value=mock_graph), \
         patch("backend.agents.nodes._capture_combined_answers"):
        out = nodes.compound_node(state)

    answer = out["result"]["answer"]
    assert "October" in answer or "September" in answer


def test_compound_node_uses_llm_answer_when_all_parts_have_facts(monkeypatch, state):
    from backend.agents import nodes

    sub1 = _sub("leave_status",      "You have no leave in October.",       facts=LEAVE_FACTS)
    sub2 = _sub("attendance_records", "You have 22 records in September.",   facts=ATT_FACTS)

    mock_graph = MagicMock()
    mock_graph.invoke.side_effect = lambda s: {
        "result": sub1 if "leave" in s["question"].lower() else sub2
    }

    llm_answer = (
        "You have no leave requests in October 2026. "
        "You have 22 attendance days for September 2026: 18 present, 3 late, 1 absent."
    )

    monkeypatch.setattr(nodes, "split_compound_question", lambda _: [
        "Show my leave in October",
        "Show my attendance in September",
    ])
    monkeypatch.setattr(nodes.settings, "llm_narration_enabled", True)
    monkeypatch.setattr(nodes, "write_answer", lambda _q, _f: llm_answer)
    monkeypatch.setattr(nodes, "compound_answer_check_failure", lambda a, f, pf: None)

    with patch("backend.agents.nodes.get_chat_graph", return_value=mock_graph), \
         patch("backend.agents.nodes._capture_combined_answers"):
        out = nodes.compound_node(state)

    assert out["result"]["answer"] == llm_answer
    assert out["result"]["message"] == llm_answer


def test_compound_node_keeps_template_on_check_failure(monkeypatch, state):
    from backend.agents import nodes

    sub1 = _sub("leave_status",      "You have no leave in October.",      facts=LEAVE_FACTS)
    sub2 = _sub("attendance_records", "You have 22 records in September.", facts=ATT_FACTS)

    mock_graph = MagicMock()
    mock_graph.invoke.side_effect = lambda s: {
        "result": sub1 if "leave" in s["question"].lower() else sub2
    }

    monkeypatch.setattr(nodes, "split_compound_question", lambda _: [
        "Show my leave in October",
        "Show my attendance in September",
    ])
    monkeypatch.setattr(nodes.settings, "llm_narration_enabled", True)
    monkeypatch.setattr(nodes, "write_answer", lambda _q, _f: "Bad answer with 999.")
    monkeypatch.setattr(nodes, "compound_answer_check_failure", lambda a, f, pf: "number_not_in_facts")

    with patch("backend.agents.nodes.get_chat_graph", return_value=mock_graph), \
         patch("backend.agents.nodes._capture_combined_answers"):
        out = nodes.compound_node(state)

    assert "999" not in out["result"]["answer"]


# ---------------------------------------------------------------------------
# 3.  compound_answer_check_failure
# ---------------------------------------------------------------------------

from backend.services.answer_writer import compound_answer_check_failure, all_parts_covered


class TestCompoundAnswerCheckFailure:

    def test_happy_leave_and_attendance(self):
        parts = [LEAVE_FACTS, ATT_FACTS]
        answer = (
            "You have no leave requests in October 2026. "
            "You have 22 attendance days for September 2026: 18 present, 3 late, 1 absent."
        )
        assert compound_answer_check_failure(answer, _merged(parts), parts) is None

    def test_happy_leave_and_holidays(self):
        parts = [LEAVE_FACTS, HOLIDAY_FACTS]
        answer = (
            "You have no leave requests in October 2026. "
            "There are no holidays in November 2026."
        )
        assert compound_answer_check_failure(answer, _merged(parts), parts) is None

    def test_too_short(self):
        parts = [LEAVE_FACTS, ATT_FACTS]
        assert compound_answer_check_failure("No.", _merged(parts), parts) == "too_short"

    def test_invented_number_rejected(self):
        parts = [LEAVE_FACTS, ATT_FACTS]
        answer = (
            "You have 999 leave requests in October 2026. "
            "You have 22 attendance days in September 2026."
        )
        assert compound_answer_check_failure(answer, _merged(parts), parts) == "number_not_in_facts"

    def test_month_not_in_any_part_rejected(self):
        parts = [LEAVE_FACTS, ATT_FACTS]
        answer = (
            "You have no leave requests in July 2026. "
            "You have 22 attendance days in September 2026."
        )
        assert compound_answer_check_failure(answer, _merged(parts), parts) == "month_not_in_period"

    def test_first_person_I_rejected(self):
        parts = [LEAVE_FACTS, ATT_FACTS]
        answer = (
            "You have no leave requests in October 2026. "
            "I found 22 attendance days in September 2026."
        )
        assert compound_answer_check_failure(answer, _merged(parts), parts) == "first_person_I"

    def test_parts_not_covered(self):
        parts = [LEAVE_FACTS, ATT_FACTS]
        answer = "You have no leave requests in October 2026."
        assert compound_answer_check_failure(answer, _merged(parts), parts) == "parts_not_covered"

    def test_numbers_from_all_parts_allowed(self):
        parts = [LEAVE_FACTS, ATT_FACTS]
        answer = (
            "You have no leave requests in October 2026. "
            "You have 22 attendance days for September 2026: 18 present, 3 late, 1 absent."
        )
        assert compound_answer_check_failure(answer, _merged(parts), parts) is None

    def test_cross_part_months_allowed(self):
        parts = [LEAVE_FACTS, ATT_FACTS]
        merged = {
            "compound": True, "period_text": "September 2026 to October 2026",
            "parts": [{"order": 1, **LEAVE_FACTS}, {"order": 2, **ATT_FACTS}],
        }
        answer = (
            "You have no leave requests in October 2026. "
            "You have 22 attendance days for September 2026."
        )
        assert compound_answer_check_failure(answer, merged, parts) is None

    def test_unit_grammar_rejected(self):
        parts = [LEAVE_FACTS, ATT_FACTS]
        answer = (
            "You have no leave requests in October 2026. "
            "You have 1 days in September 2026."
        )
        assert compound_answer_check_failure(answer, _merged(parts), parts) == "unit_grammar"


# ---------------------------------------------------------------------------
# 4.  all_parts_covered
# ---------------------------------------------------------------------------

class TestAllPartsCovered:

    def test_both_entities_present(self):
        answer = "You have no leave requests in October 2026. You have 22 attendance days."
        assert all_parts_covered(answer, [LEAVE_FACTS, ATT_SEP]) is True

    def test_missing_entity_fails(self):
        answer = "You have no leave requests in October 2026."
        assert all_parts_covered(answer, [LEAVE_FACTS, ATT_SEP]) is False

    def test_same_entity_twice(self):
        answer = (
            "You have 22 attendance days in September 2026. "
            "You have 16 attendance days in October 2026."
        )
        assert all_parts_covered(answer, [ATT_SEP, ATT_OCT]) is True

    def test_no_parts_always_passes(self):
        assert all_parts_covered("Any answer.", []) is True

    def test_empty_answer_fails_when_parts_exist(self):
        assert all_parts_covered("", [LEAVE_FACTS, ATT_SEP]) is False