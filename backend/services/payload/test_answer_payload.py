from datetime import date
from decimal import Decimal

import pytest

from backend.services.payload.answer_payload import compute_facts

PERIOD = {"start_date": "2026-10-01", "end_date": "2026-10-31"}


def spec(label, unit, unit_singular, fields, **overrides):
    return {
        "label": label,
        "unit": unit,
        "unit_singular": unit_singular,
        "field_labels": fields,
        "narratable": True,
        "sensitive": False,
        **overrides,
    }


@pytest.mark.parametrize(
    ("entity", "label", "unit", "singular"),
    [
        ("leave_request", "leave request", "leave requests", "leave request"),
        (
            "wfh_request",
            "work from home request",
            "work-from-home requests",
            "work-from-home request",
        ),
        ("timesheet", "timesheet", "timesheets", "timesheet"),
        ("holiday", "holiday", "holidays", "holiday"),
        ("task", "task", "tasks", "task"),
    ],
)
def test_non_attendance_entity_count_facts(entity, label, unit, singular):
    facts = compute_facts(
        "How many records?",
        {"operation_id": f"{entity}.count", "filters": {"status": "PENDING"}},
        PERIOD,
        {"data": {"count": 2}},
        {entity: spec(label, unit, singular, {"status": "status"})},
    )

    assert facts["shape"] == "count"
    assert facts["entity"] == label
    assert facts["unit"] == unit
    assert facts["unit_singular"] == singular
    assert facts["count"] == 2
    assert facts["status"] == "pending"
    assert facts["found"] is True


def test_leave_balance_sum_uses_the_registered_field_label():
    facts = compute_facts(
        "What is my allocated leave?",
        {
            "operation_id": "leave_balance.sum",
            "aggregate_field": "allocated_days",
            "filters": {},
        },
        PERIOD,
        {"data": {"field": "allocated_days", "total": Decimal("12.5")}},
        {
            "leave_balance": spec(
                "leave balance",
                "days",
                "day",
                {"allocated_days": "allocated"},
            )
        },
    )

    assert facts["shape"] == "sum"
    assert facts["measure"] == "allocated"
    assert facts["total"] == "12.5"


def test_task_status_groups_are_labelled_and_counted():
    facts = compute_facts(
        "Show task status breakdown",
        {
            "operation_id": "task.group_by",
            "group_by_field": "status",
            "aggregate_function": "count",
            "filters": {},
        },
        PERIOD,
        {
            "data": [
                {"group_value": "in_progress", "record_count": 3},
                {"group_value": "completed", "record_count": 1},
            ]
        },
        {"task": spec("task", "tasks", "task", {"status": "status"})},
    )

    assert facts["groups"] == [
        {"label": "in progress", "count": 3},
        {"label": "completed", "count": 1},
    ]


def test_employee_facts_do_not_expose_manager_only_task_score():
    facts = compute_facts(
        "What is my task score?",
        {
            "operation_id": "task.sum",
            "aggregate_field": "performance_score",
            "filters": {},
        },
        PERIOD,
        {"data": {"field": "performance_score", "total": 4.5}},
        {
            "task": spec(
                "task",
                "tasks",
                "task",
                {"performance_score": "performance score"},
            )
        },
        role="employee",
    )

    assert facts is None


def test_list_facts_only_include_fields_from_the_entity_map():
    facts = compute_facts(
        "Show my leave requests",
        {"operation_id": "leave_request.list", "filters": {}},
        PERIOD,
        {
            "data": [
                {
                    "start_date": date(2026, 10, 3),
                    "status": "APPROVED",
                    "reason": "private",
                    "employee_id": 41,
                }
            ]
        },
        {
            "leave_request": spec(
                "leave request",
                "leave requests",
                "leave request",
                {"start_date": "start date", "status": "status"},
            )
        },
    )

    assert facts["shape"] == "single_record"
    assert facts["record"] == {
        "start date": "2026-10-03",
        "status": "approved",
    }


def test_attendance_minutes_are_split_without_raw_total():
    facts = compute_facts(
        "How much overtime?",
        {
            "operation_id": "attendance.list",
            "aggregate_field": "overtime_minutes",
            "filters": {},
        },
        PERIOD,
        {"data": [{"overtime_minutes": 79}]},
        {
            "attendance": spec(
                "attendance",
                "days",
                "day",
                {"overtime_minutes": "overtime"},
            )
        },
    )

    assert facts["measure"] == "overtime"
    assert facts["hours"] == 1
    assert facts["minutes"] == 19
    assert "total_minutes" not in facts


@pytest.mark.parametrize("entity", ["loan_request", "payroll_summary"])
def test_sensitive_financial_entity_facts_are_not_generated(entity):
    facts = compute_facts(
        "What is the amount?",
        {"operation_id": f"{entity}.list", "filters": {}},
        PERIOD,
        {"data": [{"total_amount": Decimal("125.50"), "currency": "INR"}]},
        {
            entity: spec(
                entity,
                "records",
                "record",
                {"total_amount": "total amount", "currency": "currency"},
                sensitive=True,
                narratable=False,
            )
        },
    )

    assert facts is None
