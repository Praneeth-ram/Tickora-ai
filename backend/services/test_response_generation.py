from datetime import date
from decimal import Decimal
from unittest.mock import patch

from backend.services.answer_builder import fmt_range
from backend.services.llm_chat_service import (
    _loan_component_phrase,
    _loan_metric_field,
    _answer_status_check,
    _answer_timesheet,
    count_response,
    format_timesheet_response,
    grouped_response,
    leave_type_response,
    loan_amount_response,
    normalize_and_correct_plan,
    _payroll_response,
    run_llm_chat,
    sum_response,
    task_count_response,
    _result,
)
from backend.services.request_answer_builder import request_answer


def test_payroll_response_detects_net_salary_without_regex_type_error():
    response = _payroll_response(
        [{
            "period_start": date(2026, 10, 1),
            "period_end": date(2026, 10, 31),
            "net_amount": Decimal("4250.00"),
            "currency": "USD",
        }],
        {},
        "What is my net salary?",
    )

    assert response == (
        "Your net salary:\n"
        "- Net salary for October 2026: USD 4,250.00."
    )


def test_result_keeps_structured_and_raw_data_when_table_is_hidden():
    structured = {"count": 4}
    raw = {"record_count": 4}

    response = _result(
        "How many tasks?",
        "There are 4 tasks.",
        "task_lookup",
        {"start_date": None, "end_date": None},
        False,
        structured,
        raw,
    )

    assert response["show_table"] is False
    assert response["data"] == structured
    assert response["raw_data"] == raw


def test_status_check_returns_the_matching_structured_and_raw_rows():
    raw_rows = [{
        "start_date": date(2026, 10, 5),
        "applied_at": date(2026, 9, 30),
        "status": "approved",
    }]
    with patch(
        "backend.services.llm_chat_service._execute",
        return_value={"data": raw_rows},
    ):
        response = _answer_status_check(
            "Was my leave approved?",
            "Was my leave approved?",
            {"operation_id": "leave_request.list", "filters": {}},
            {"start_date": None, "end_date": None},
            12,
            "approved",
        )

    assert response["show_table"] is False
    assert response["data"][0]["requested_at"] == date(2026, 9, 30)
    assert response["raw_data"] == raw_rows


def test_timesheet_status_returns_structured_and_raw_rows():
    raw_rows = [{
        "period_start": date(2026, 10, 5),
        "period_end": date(2026, 10, 11),
        "status": "approved",
    }]
    with patch(
        "backend.services.llm_chat_service._execute",
        return_value={"data": raw_rows},
    ):
        response = _answer_timesheet(
            "What is my latest timesheet status?",
            "What is my latest timesheet status?",
            {"start_date": None, "end_date": None},
            12,
            None,
        )

    assert response["show_table"] is False
    assert response["data"][0]["work_date"] == date(2026, 10, 5)
    assert response["data"][0]["submission_status"] == "approved"
    assert response["raw_data"] == raw_rows


def test_leave_type_lookup_passes_authenticated_organization():
    with patch(
        "backend.services.llm_chat_service._execute",
        return_value={
            "data": [
                {
                    "id": 3,
                    "code": "VAC",
                    "name": "Vacation",
                    "is_paid": True,
                }
            ]
        },
    ) as execute:
        response = run_llm_chat(
            "Show all available leave types.",
            employee_id=12,
            organization_id=7,
        )

    assert execute.call_args.kwargs["organization_id"] == 7
    assert execute.call_args.args[0]["operation_id"] == "leave_type.list"
    assert response["data"][0]["name"] == "Vacation"
    assert response["raw_data"] == response["data"]


def test_count_answers_use_entity_names_and_singular_grammar():
    assert count_response("leave_request", 1, "approved", "in October 2026") == (
        "You have 1 approved leave request in October 2026."
    )
    assert count_response("holiday", 0, None, "in October 2026") == (
        "No holidays were found in October 2026."
    )


def test_task_count_answers_describe_task_filters_and_periods():
    cases = [
        (
            5,
            {},
            "How many tasks are there?",
            "",
            12,
            "There are 5 tasks.",
        ),
        (
            5,
            {"assigned_to_employee_id": 12},
            "How many tasks are assigned to me?",
            "",
            12,
            "You have 5 tasks assigned to you.",
        ),
        (
            3,
            {"status": "completed"},
            "How many completed tasks are there?",
            "",
            12,
            "There are 3 completed tasks.",
        ),
        (
            2,
            {"managed_by_employee_id": 12},
            "How many tasks am I managing?",
            "",
            12,
            "You manage 2 tasks.",
        ),
        (
            4,
            {"project_id": 27},
            "How many tasks are in project 27?",
            "",
            12,
            "There are 4 tasks for project 27.",
        ),
        (
            6,
            {},
            "How many tasks are there in October 2026?",
            "in October 2026",
            12,
            "There are 6 tasks in October 2026.",
        ),
        (
            1,
            {"status": "completed"},
            "How many completed tasks are there?",
            "from 1 to 15 October 2026",
            12,
            "There is 1 completed task from 1 to 15 October 2026.",
        ),
        (
            3,
            {},
            "How many tasks are in my organization?",
            "",
            12,
            "There are 3 tasks in your organization that you're assigned to or manage.",
        ),
        (
            2,
            {"assigned_to_employee_id": 34},
            "How many tasks are assigned to employee 34?",
            "",
            12,
            "There are 2 tasks assigned to employee 34.",
        ),
        (
            0,
            {"status": "completed"},
            "How many completed tasks are there?",
            "",
            12,
            "No completed tasks were found.",
        ),
    ]

    for count, filters, question, span, employee_id, expected in cases:
        assert task_count_response(
            count, filters, question, span, employee_id
        ) == expected


def test_multi_status_task_count_groups_by_status_without_status_filter():
    task_definition = {
        "filters": ["status", "project_id", "task_date"],
        "identity_filters": {},
        "aggregate_fields": ["performance_score"],
    }
    registry = {
        "task.count": task_definition,
        "task.sum": task_definition,
        "task.group_by": task_definition,
    }

    with patch(
        "backend.services.llm_chat_service.build_operation_registry",
        return_value=registry,
    ):
        grouped_plan, _ = normalize_and_correct_plan(
            {"operation_id": "task.count", "filters": {"status": "pending"}},
            "How many tasks are pending, completed, and in progress?",
            date(2026, 10, 30),
        )
        single_status_plan, _ = normalize_and_correct_plan(
            {"operation_id": "task.list", "filters": {}},
            "How many completed tasks are there?",
            date(2026, 10, 30),
        )

    assert grouped_plan["operation_id"] == "task.group_by"
    assert grouped_plan["group_by_field"] == "status"
    assert grouped_plan["aggregate_function"] == "count"
    assert "status" not in grouped_plan["filters"]
    assert single_status_plan["operation_id"] == "task.count"
    assert single_status_plan["filters"]["status"] == "completed"


def test_grouping_explicitly_named_entity_overrides_wrong_model_entity():
    timesheet_definition = {
        "entity": "timesheet",
        "table": "timesheets",
        "fields": ["period_start", "period_end", "status"],
        "filters": ["period_start", "status"],
        "identity_filters": {},
        "date_field": "period_start",
        "date_fields": ["period_start", "submitted_at"],
        "group_by_fields": ["status"],
    }
    registry = {
        "timesheet.list": timesheet_definition,
        "timesheet.count": timesheet_definition,
        "timesheet.group_by": {
            **timesheet_definition,
            "group_by_fields": ["status"],
        },
    }

    with patch(
        "backend.services.llm_chat_service.build_operation_registry",
        return_value=registry,
    ):
        plan, period = normalize_and_correct_plan(
            {
                "operation_id": "attendance.list",
                "filters": {"attendance_date": {"gte": "2026-10-01"}},
            },
            "Group my timesheets by status.",
            date(2026, 10, 31),
        )

    assert plan["operation_id"] == "timesheet.group_by"
    assert plan["group_by_field"] == "status"
    assert plan["aggregate_function"] == "count"
    assert "attendance_date" not in plan["filters"]
    assert period == {"start_date": None, "end_date": None}


def test_loan_component_and_metric_are_resolved_without_component_constants():
    fields = ["total_amount", "deducted_amount", "remaining_amount"]
    question = "What is the deducted amount for Penalty Deduction?"
    metric = _loan_metric_field(question, fields)

    assert metric == "deducted_amount"
    assert _loan_component_phrase(question, metric) == "Penalty Deduction"
    assert _loan_component_phrase(
        "Show my approved loan requests.",
        None,
    ) is None
    assert _loan_metric_field(
        "What is the remaining amount for Emergency Loan?",
        fields,
    ) == "remaining_amount"


def test_approved_loan_request_list_does_not_add_status_as_component():
    loan_definition = {
        "fields": [
            "component",
            "total_amount",
            "deducted_amount",
            "remaining_amount",
            "status",
        ],
        "filters": [
            "employee_id",
            "managed_by_employee_id",
            "component",
            "status",
        ],
        "identity_filters": {
            "employee_id": "employee_id",
            "managed_by_employee_id": "employee_id",
        },
        "aggregate_fields": [
            "total_amount",
            "deducted_amount",
            "remaining_amount",
        ],
    }
    registry = {
        "loan_request.list": loan_definition,
        "loan_request.sum": loan_definition,
        "loan_request.count": loan_definition,
    }
    approved_record = {
        "component": "Emergency Loan",
        "status": "approved",
    }

    with (
        patch(
            "backend.services.llm_chat_service.get_query_plan",
            return_value={
                "operation_id": "loan_request.list",
                "filters": {"status": "approved"},
            },
        ),
        patch(
            "backend.services.llm_chat_service._approved_operations",
            return_value=frozenset({"loan_request.list"}),
        ),
        patch(
            "backend.services.llm_chat_service.build_operation_registry",
            return_value=registry,
        ),
        patch(
            "backend.services.llm_chat_service._execute",
            return_value={
                "operation_id": "loan_request.list",
                "operation": "list",
                "entity": "loan_request",
                "data": [approved_record],
            },
        ) as execute,
    ):
        response = run_llm_chat(
            "Show my approved loan requests.",
            employee_id=1,
            organization_id=1,
        )

    final_plan = execute.call_args.args[0]
    assert execute.call_count == 1
    assert final_plan["filters"]["status"] == "approved"
    assert "component" not in final_plan["filters"]
    assert response["data"] == [approved_record]


def test_loan_amount_response_uses_database_value_and_missing_record_message():
    assert loan_amount_response(
        [{"component": "Emergency Loan", "remaining_amount": Decimal("1250.50")}],
        "remaining_amount",
        "Emergency Loan",
    ) == "The remaining amount for Emergency Loan is 1,250.50."
    assert loan_amount_response(
        [],
        "deducted_amount",
        "Penalty Deduction",
    ) == "No loan records were found for Penalty Deduction."


def test_loan_amount_query_filters_component_and_returns_requested_metric():
    loan_definition = {
        "fields": [
            "component",
            "total_amount",
            "deducted_amount",
            "remaining_amount",
        ],
        "filters": ["employee_id", "managed_by_employee_id", "component"],
        "identity_filters": {
            "employee_id": "employee_id",
            "managed_by_employee_id": "employee_id",
        },
        "aggregate_fields": [
            "total_amount",
            "deducted_amount",
            "remaining_amount",
        ],
    }
    registry = {
        "loan_request.list": loan_definition,
        "loan_request.sum": loan_definition,
    }
    component_result = {
        "operation_id": "loan_request.list",
        "entity": "loan_request",
        "operation": "list",
        "data": [{"component": "Penalty Deduction"}],
    }
    records_result = {
        "operation_id": "loan_request.list",
        "entity": "loan_request",
        "operation": "list",
        "data": [{
            "component": "Penalty Deduction",
            "deducted_amount": Decimal("250.00"),
        }],
    }

    with (
        patch(
            "backend.services.llm_chat_service.get_query_plan",
            return_value={"operation_id": "loan_request.list", "filters": {}},
        ),
        patch(
            "backend.services.llm_chat_service._approved_operations",
            return_value=frozenset({"loan_request.list"}),
        ),
        patch(
            "backend.services.llm_chat_service.build_operation_registry",
            return_value=registry,
        ),
        patch(
            "backend.services.llm_chat_service._execute",
            side_effect=[component_result, records_result],
        ) as execute,
    ):
        response = run_llm_chat(
            "What is the deducted amount for Penalty Deduction loan?",
            employee_id=12,
            organization_id=7,
        )

    final_plan = execute.call_args_list[-1].args[0]
    assert final_plan["filters"]["component"] == "Penalty Deduction"
    assert final_plan["fields"] == ["component", "deducted_amount"]
    assert response["answer"] == (
        "The deducted amount for Penalty Deduction is 250.00."
    )
    assert response["intent"] == "loan_lookup"


def test_sum_answers_humanize_metrics_and_decimal_results():
    assert sum_response("worked_minutes", Decimal("510"), "in October 2026") == (
        "You worked 8 hours and 30 minutes in October 2026."
    )
    assert sum_response("allocated_days", Decimal("1"), "in 2026") == (
        "Your total allocated leave in 2026 is 1 day."
    )


def test_grouped_answer_formats_statuses_as_a_summary():
    assert grouped_response(
        "attendance",
        [
            {"group_value": "PRESENT", "record_count": 4},
            {"group_value": "LATE", "record_count": 1},
        ],
        "status",
        "count",
        None,
        "in October 2026",
    ) == (
        "Your attendance breakdown by status in October 2026: "
        "present: 4 days, late: 1 day."
    )


def test_grouped_task_count_uses_task_labels_and_pluralization():
    assert grouped_response(
        "task",
        [
            {"group_value": "completed", "record_count": 1},
            {"group_value": "in_progress", "record_count": 2},
            {"group_value": "pending", "record_count": 3},
        ],
        "status",
        "count",
        None,
        "",
    ) == (
        "Your task breakdown by status: "
        "completed: 1 task, in progress: 2 tasks, pending: 3 tasks."
    )


def test_empty_grouped_task_response_names_tasks():
    assert grouped_response(
        "task", [], "status", "count", None, ""
    ) == "No task breakdown is available."


def test_timesheet_answer_formats_periods_and_caps_long_lists():
    rows = [
        {
            "period_start": date(2026, 10, 5),
            "period_end": date(2026, 10, 11),
            "status": "APPROVED",
        }
    ]
    assert format_timesheet_response(rows) == (
        "Your timesheet:\n- 5 to 11 October 2026: Approved"
    )


def test_leave_types_are_named_without_exposing_database_ids():
    assert leave_type_response(
        [{"id": 3, "name": "Sick Leave", "is_paid": True}]
    ) == "There is 1 leave type: Sick Leave (paid)."


def test_request_answer_uses_concise_status_summary():
    answer = request_answer(
        "leave",
        [
            {"status": "approved", "start_date": date(2026, 10, 5), "end_date": date(2026, 10, 5)},
            {"status": "pending", "start_date": date(2026, 10, 12), "end_date": date(2026, 10, 12)},
        ],
        "show my leave requests",
        "in October 2026",
        False,
    )
    assert answer == "You have 2 leave requests in October 2026: 1 pending and 1 approved."


def test_single_request_summary_does_not_repeat_the_count():
    answer = request_answer(
        "leave",
        [{"status": "approved"}],
        "show my leave request",
        "",
        False,
    )
    assert answer == "Your leave request is approved."


def test_fractional_request_days_are_not_truncated():
    answer = request_answer(
        "leave",
        [{
            "status": "approved",
            "start_date": date(2026, 10, 5),
            "end_date": date(2026, 10, 5),
            "requested_days": 0.5,
        }],
        "how many days",
        "",
        False,
    )
    assert answer == "Your leave request for 5 October 2026 covers 0.5 days."


def test_date_range_helper_remains_human_readable():
    assert fmt_range(date(2026, 10, 1), date(2026, 10, 31)) == "October 2026"
