from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from backend.agents import nodes
from backend.services.answer_router import choose_route


def test_only_explicit_table_and_list_requests_skip_narration():
    assert choose_route("Show my leave requests") == "table"
    assert choose_route("Could you create a table of my tasks?") == "table"
    assert choose_route("What are the details of my leave requests?") == "llm"
    assert choose_route("What is my timesheet status?") == "llm"


def test_specific_question_is_narrated_even_when_a_table_is_shown():
    question = "What are the details of my leave requests for October 2026?"
    result = {
        "intent": "leave_status",
        "answer": "Here are your leave requests.",
        "message": "Here are your leave requests.",
        "show_table": True,
        "data": [
            {"start_date": date(2026, 10, day), "status": "APPROVED"}
            for day in range(1, 7)
        ],
    }
    spec = {
        "label": "leave request",
        "unit": "leave requests",
        "unit_singular": "leave request",
        "field_labels": {"start_date": "start date", "status": "status"},
        "narratable": True,
        "sensitive": False,
        "scope": "employee_id",
    }

    with (
        patch.object(nodes, "settings") as settings,
        patch.object(nodes, "get_actor", return_value=SimpleNamespace(role="employee")),
        patch.object(nodes, "_entity_specs", return_value={"leave_request": spec}),
        patch.object(
            nodes,
            "write_answer",
            return_value="You have 6 leave requests in October 2026.",
        ) as write_answer,
    ):
        settings.llm_narration_enabled = True
        narrated = nodes._route_answer(
            question,
            dict(result),
            {"operation_id": "leave_request.list", "filters": {}},
            {"start_date": date(2026, 10, 1), "end_date": date(2026, 10, 31)},
        )

    write_answer.assert_called_once()
    assert narrated["show_table"] is True
    assert narrated["answer"] == "You have 6 leave requests in October 2026."


def test_explicit_list_request_keeps_table_template_without_narration():
    result = {
        "intent": "leave_status",
        "answer": "Here are your leave requests.",
        "message": "Here are your leave requests.",
        "show_table": True,
        "data": [{"status": "APPROVED"}],
    }

    with (
        patch.object(nodes, "settings") as settings,
        patch.object(nodes, "write_answer") as write_answer,
    ):
        settings.llm_narration_enabled = True
        response = nodes._route_answer(
            "Show my leave requests",
            dict(result),
            {"operation_id": "leave_request.list", "filters": {}},
            {"start_date": None, "end_date": None},
        )

    write_answer.assert_not_called()
    assert response["answer"] == result["answer"]


def test_timesheet_narration_uses_raw_fields_instead_of_display_aliases():
    question = "What are my timesheet details for October 2026?"
    result = {
        "intent": "timesheet_lookup",
        "answer": "Your timesheet is listed below.",
        "message": "Your timesheet is listed below.",
        "show_table": True,
        "data": [{
            "work_date": date(2026, 10, 5),
            "submission_status": "approved",
        }],
        "raw_data": [{
            "period_start": date(2026, 10, 5),
            "period_end": date(2026, 10, 11),
            "status": "approved",
        }],
    }
    spec = {
        "label": "timesheet",
        "unit": "timesheets",
        "unit_singular": "timesheet",
        "field_labels": {
            "period_start": "period start",
            "period_end": "period end",
            "status": "status",
        },
        "narratable": True,
        "sensitive": False,
        "scope": "employee_id",
    }

    def answer_with_raw_facts(_question, facts):
        assert facts["record"]["period start"] == "2026-10-05"
        assert facts["record"]["status"] == "approved"
        return "Your timesheet was approved in October 2026."

    with (
        patch.object(nodes, "settings") as settings,
        patch.object(nodes, "get_actor", return_value=SimpleNamespace(role="employee")),
        patch.object(nodes, "_entity_specs", return_value={"timesheet": spec}),
        patch.object(nodes, "write_answer", side_effect=answer_with_raw_facts) as write_answer,
    ):
        settings.llm_narration_enabled = True
        response = nodes._route_answer(
            question,
            result,
            {"operation_id": "timesheet.list", "filters": {}},
            {"start_date": date(2026, 10, 1), "end_date": date(2026, 10, 31)},
        )

    write_answer.assert_called_once()
    assert response["answer"] == "Your timesheet was approved in October 2026."
