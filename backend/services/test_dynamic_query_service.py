import pytest
from sqlalchemy import create_engine
from backend.exceptions import BadRequestError
from backend.services.dynamic_query_service import (
    QueryPlanError,
    execute_query_plan,
)
from backend.services.operation_registry import build_operation_registry
from backend.security.access_policy import Actor, EMPLOYEE, reset_actor, set_actor
from unittest.mock import MagicMock, patch


def execute_as_actor(plan, **kwargs):
    employee_id = kwargs["employee_id"]
    organization_id = kwargs.get("organization_id") or 1
    token = set_actor(Actor(employee_id, organization_id, None, EMPLOYEE))
    try:
        return execute_query_plan(plan, **kwargs)
    finally:
        reset_actor(token)


def execute_without_database(plan):
    attendance_columns = [
        "employee_id",
        "attendance_date",
        "clock_in",
        "clock_out",
        "status",
        "work_location",
        "worked_minutes",
        "overtime_minutes",
        "is_late",
    ]

    mock_catalog = {
        "attendance_records": {
            "schema": "public",
            "columns": [
                {
                    "name": name,
                    "type": "TEXT",
                    "nullable": True,
                    "primary_key": False,
                }
                for name in attendance_columns
            ],
            "foreign_keys": [],
        }
    }

    with patch(
        "backend.services.operation_registry.discover_schema",
        return_value=mock_catalog,
    ):
        return execute_as_actor(plan, employee_id=1)


def loan_query_setup():
    loan_columns = [
        "id",
        "organization_id",
        "employee_id",
        "managed_by_employee_id",
        "component",
        "mode",
        "total_amount",
        "deducted_amount",
        "remaining_amount",
        "installment_amount",
        "installments",
        "installments_paid",
        "start_month",
        "next_deduction",
        "remarks",
        "status",
        "loan_status",
        "created_at",
    ]
    employee_columns = [
        "id",
        "organization_id",
        "full_name",
        "employee_code",
    ]
    schema = {
        "loan_requests": {
            "schema": "public",
            "columns": [
                {"name": name, "type": "TEXT"}
                for name in loan_columns
            ],
            "foreign_keys": [],
        },
        "employees": {
            "schema": "public",
            "columns": [
                {"name": name, "type": "TEXT"}
                for name in employee_columns
            ],
            "foreign_keys": [],
        },
    }
    engine = create_engine("sqlite://")
    connection = MagicMock()
    connection.execute.return_value.mappings.return_value.all.return_value = [
        {
            "component": "Emergency Loan",
            "employee_name": "Employee",
            "employee_code": "EMP001",
            "managed_by_name": None,
            "managed_by_code": None,
        }
    ]
    engine.connect = MagicMock()
    engine.connect.return_value.__enter__.return_value = connection
    return schema, engine, connection


def test_rejects_unapproved_aggregate_field():
    plan = {
        "operation_id": "attendance.sum",
        "aggregate_field": "salary",
    }

    with pytest.raises(QueryPlanError):
        execute_without_database(plan)


def test_sum_query_separates_alias_from_from_clause():
    plan = {
        "operation_id": "attendance.sum",
        "aggregate_field": "worked_minutes",
    }
    engine = create_engine("sqlite://")
    connection = MagicMock()
    connection.execute.return_value.mappings.return_value.all.return_value = [
        {"total": 0}
    ]
    engine.connect = MagicMock()
    engine.connect.return_value.__enter__.return_value = connection

    with patch(
        "backend.services.operation_registry.discover_schema",
        return_value={
            "attendance_records": {
                "schema": "public",
                "columns": [
                    {"name": name, "type": "INTEGER"}
                    for name in (
                        "employee_id",
                        "attendance_date",
                        "worked_minutes",
                        "overtime_minutes",
                        "status",
                        "work_location",
                        "is_late",
                    )
                ],
                "foreign_keys": [],
            }
        },
    ):
        execute_as_actor(plan, employee_id=1, db_engine=engine)

    generated_sql = str(connection.execute.call_args.args[0])
    assert "AS total FROM " in generated_sql
    assert "AS totalFROM " not in generated_sql


def test_organization_scoped_leave_type_list_is_registered_and_filtered():
    plan = {
        "operation_id": "leave_type.list",
        "fields": ["code", "name", "is_paid"],
        "filters": {},
    }
    engine = create_engine("sqlite://")
    connection = MagicMock()
    connection.execute.return_value.mappings.return_value.all.return_value = [
        {"code": "VAC", "name": "Vacation", "is_paid": True}
    ]
    engine.connect = MagicMock()
    engine.connect.return_value.__enter__.return_value = connection

    with patch(
        "backend.services.operation_registry.discover_schema",
        return_value={
            "leave_types": {
                "schema": "public",
                "columns": [
                    {"name": name, "type": "INTEGER"}
                    for name in (
                        "id",
                        "code",
                        "name",
                        "is_paid",
                        "organization_id",
                    )
                ],
                "foreign_keys": [],
            }
        },
    ):
        result = execute_as_actor(
            plan,
            employee_id=1,
            organization_id=7,
            db_engine=engine,
        )

    generated_sql, parameters = connection.execute.call_args.args
    assert result["operation_id"] == "leave_type.list"
    assert result["data"] == [
        {"code": "VAC", "name": "Vacation", "is_paid": True}
    ]
    assert "organization_id = :authenticated_organization_id" in str(
        generated_sql
    )
    assert parameters["authenticated_organization_id"] == 7


def test_loan_start_month_filter_expands_iso_month_to_valid_date_range():
    plan = {
        "operation_id": "loan_request.list",
        "fields": ["component"],
        "filters": {
            "start_month": "2026-10",
        },
    }
    schema, engine, connection = loan_query_setup()

    with patch(
        "backend.services.operation_registry.discover_schema",
        return_value=schema,
    ):
        result = execute_as_actor(
            plan,
            employee_id=1,
            organization_id=1,
            db_engine=engine,
        )

    generated_sql, parameters = connection.execute.call_args.args
    sql = str(generated_sql)
    assert result["data"][0]["component"] == "Emergency Loan"
    assert "CAST(lr.start_month AS DATE) >= :loan_start_month_gte" in sql
    assert "CAST(lr.start_month AS DATE) <= :loan_start_month_lte" in sql
    assert parameters["loan_start_month_gte"].isoformat() == "2026-10-01"
    assert parameters["loan_start_month_lte"].isoformat() == "2026-10-31"


def test_loan_date_filter_accepts_a_single_day():
    plan = {
        "operation_id": "loan_request.list",
        "fields": ["component"],
        "filters": {
            "start_month": {
                "gte": "2026-10-02",
                "lte": "2026-10-02",
            },
        },
    }
    schema, engine, connection = loan_query_setup()

    with patch(
        "backend.services.operation_registry.discover_schema",
        return_value=schema,
    ):
        execute_as_actor(
            plan,
            employee_id=1,
            organization_id=1,
            db_engine=engine,
        )

    generated_sql, parameters = connection.execute.call_args.args
    assert "CAST(lr.start_month AS DATE) >= :loan_start_month_gte" in str(
        generated_sql
    )
    assert "CAST(lr.start_month AS DATE) <= :loan_start_month_lte" in str(
        generated_sql
    )
    assert parameters["loan_start_month_gte"] == parameters["loan_start_month_lte"]


@pytest.mark.parametrize(
    "operation_id",
    ["loan_request.list", "loan_request.count"],
)
def test_loan_date_filter_rejects_inverted_range_with_bad_request(
    operation_id,
):
    plan = {
        "operation_id": operation_id,
        "filters": {
            "start_month": {
                "gte": "2026-10-03",
                "lte": "2026-10-02",
            },
        },
    }
    schema, engine, _ = loan_query_setup()

    with patch(
        "backend.services.operation_registry.discover_schema",
        return_value=schema,
    ):
        with pytest.raises(BadRequestError):
            execute_as_actor(
                plan,
                employee_id=1,
                organization_id=1,
                db_engine=engine,
            )


def test_timesheet_status_grouping_is_registered_from_entity_policy():
    timesheet_columns = [
        "employee_id",
        "period_start",
        "period_end",
        "status",
        "submitted_at",
        "approved_at",
    ]

    with patch(
        "backend.services.operation_registry.discover_schema",
        return_value={
            "timesheets": {
                "schema": "public",
                "columns": [
                    {"name": name, "type": "TEXT"}
                    for name in timesheet_columns
                ],
                "foreign_keys": [],
            }
        },
    ):
        registry = build_operation_registry()

    assert registry["timesheet.group_by"]["group_by_fields"] == ["status"]


def test_rejects_unapproved_grouping_field():
    plan = {
        "operation_id": "attendance.group_by",
        "group_by_field": "email",
        "aggregate_function": "count",
    }

    with pytest.raises(QueryPlanError):
        execute_without_database(plan)


def test_rejects_unsupported_aggregate_function():
    plan = {
        "operation_id": "attendance.group_by",
        "group_by_field": "status",
        "aggregate_function": "average",
    }

    with pytest.raises(QueryPlanError):
        execute_without_database(plan)


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
        execute_without_database(plan)


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

    employee_1_result = execute_as_actor(plan, employee_id=1)
    employee_2_result = execute_as_actor(plan, employee_id=2)

    assert employee_1_result["operation_id"] == "attendance.count"
    assert employee_2_result["operation_id"] == "attendance.count"


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

    result = execute_as_actor(plan, employee_id=1)

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

    result = execute_as_actor(plan, employee_id=1)

    assert result["operation"] == "count"
    assert isinstance(result["data"]["count"], int)
    assert result["data"]["count"] >= 0
