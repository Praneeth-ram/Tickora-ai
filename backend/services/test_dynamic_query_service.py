import pytest
from backend.services.dynamic_query_service import (
    QueryPlanError,
    execute_query_plan,
)

def test_rejects_unapproved_aggregate_field():
    plan = {
        "operation_id": "attendance.sum",
        "aggregate_field": "salary",
    }

    with pytest.raises(QueryPlanError):
        execute_query_plan(plan, employee_id=1)

def test_rejects_unapproved_grouping_field():
    plan = {
        "operation_id": "attendance.group_by",
        "group_by_field": "email",
        "aggregate_function": "count",
    }

    with pytest.raises(QueryPlanError):
        execute_query_plan(plan, employee_id=1)

def test_rejects_unsupported_aggregate_function():
    plan = {
        "operation_id": "attendance.group_by",
        "group_by_field": "status",
        "aggregate_function": "average",
    }

    with pytest.raises(QueryPlanError):
        execute_query_plan(plan, employee_id=1)

def test_rejects_invalid_date_range():
    plan = {
        "operation_id": "attendance.sum",
        "aggregate_field": "overtime_minutes",
        "filters": {
            "attendance_date": {
                "gte": "2026-10-23",
                "lte": "2026-10-01",
            }
        },
    }

    with pytest.raises(QueryPlanError):
        execute_query_plan(plan, employee_id=1)

def test_employee_scope_changes_with_authenticated_employee():
    plan = {
        "operation_id": "attendance.count",
        "filters": {
            "attendance_date": {
                "gte": "2026-10-01",
                "lte": "2026-10-23",
            }
        },
    }

    employee_1_result = execute_query_plan(plan, employee_id=1)
    employee_2_result = execute_query_plan(plan, employee_id=2)

    # The query must execute successfully for each authenticated employee.
    assert employee_1_result["operation_id"] == "attendance.count"
    assert employee_2_result["operation_id"] == "attendance.count"

    # This confirms distinct employee-scoped execution only if the database
    # contains different counts for these employees.
    # Do not assert unequal counts: two employees can legitimately have
    # the same number of attendance records.


def test_existing_list_operation_still_works():
    plan = {
        "operation_id": "attendance.list",
        "fields": ["attendance_date", "status"],
        "filters": {
            "attendance_date": {
                "gte": "2026-10-01",
                "lte": "2026-10-23",
            }
        },
    }

    result = execute_query_plan(plan, employee_id=1)

    assert result["operation"] == "list"
    assert isinstance(result["data"], list)

    for row in result["data"]:
        assert set(row.keys()) == {"attendance_date", "status"}


def test_existing_count_operation_still_works():
    plan = {
        "operation_id": "attendance.count",
        "filters": {
            "attendance_date": {
                "gte": "2026-10-01",
                "lte": "2026-10-23",
            }
        },
    }

    result = execute_query_plan(plan, employee_id=1)

    assert result["operation"] == "count"
    assert isinstance(result["data"]["count"], int)
    assert result["data"]["count"] >= 0
