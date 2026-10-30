import re
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from backend.services.operation_registry import build_operation_registry


_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
_MAX_LIMIT = 100


class QueryPlanError(ValueError):
    """Raised when a query plan violates the approved contract."""


def _parse_date(value: Any, label: str) -> date:
    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if not isinstance(value, str):
        raise QueryPlanError(f"{label} must be an ISO date.")

    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise QueryPlanError(
            f"{label} must be an ISO date."
        ) from exc


def execute_query_plan(
    plan: dict[str, Any],
    *,
    employee_id: int,
    schema_name: str = "public",
    db_engine: Engine | None = None,
    limit: int = 50,
    organization_id: int | None = None,
) -> dict[str, Any]:
    if (
        not isinstance(schema_name, str)
        or not _SCHEMA_RE.fullmatch(schema_name)
    ):
        raise QueryPlanError("Invalid trusted schema name.")

    if (
        not isinstance(employee_id, int)
        or isinstance(employee_id, bool)
        or employee_id <= 0
    ):
        raise QueryPlanError("Authenticated employee ID is required.")

    if organization_id is not None and (
        not isinstance(organization_id, int)
        or isinstance(organization_id, bool)
        or organization_id <= 0
    ):
        raise QueryPlanError("Authenticated organization ID is invalid.")

    if not isinstance(plan, dict):
        raise QueryPlanError("Query plan must be an object.")

    operation_id = plan.get("operation_id")
    if not isinstance(operation_id, str):
        raise QueryPlanError("operation_id is required.")

    registry = build_operation_registry(schema_name)
    definition = registry.get(operation_id)

    if definition is None:
        raise QueryPlanError(
            "Operation is not registered or available."
        )

    operation = definition["operation"]

    if operation not in {"list", "count", "sum", "group_by"}:
        raise QueryPlanError("Unsupported operation.")

    if (
        not isinstance(limit, int)
        or isinstance(limit, bool)
        or not 1 <= limit <= _MAX_LIMIT
    ):
        raise QueryPlanError(
            f"limit must be between 1 and {_MAX_LIMIT}."
        )

    # Validate fields for list operations.
    requested_fields = plan.get("fields", definition["fields"])

    if (
        not isinstance(requested_fields, list)
        or any(not isinstance(field, str) for field in requested_fields)
    ):
        raise QueryPlanError("fields must be a list of strings.")

    if operation != "list":
        if "fields" in plan and requested_fields:
            raise QueryPlanError(
                "fields can only be specified for list operations."
            )

        requested_fields = []

    elif not requested_fields:
        requested_fields = definition["fields"]

    if any(
        field not in definition["fields"]
        for field in requested_fields
    ):
        raise QueryPlanError("Requested field is not allowed.")

    aggregate_field = None
    group_by_field = None
    aggregate_function = None

    if operation == "sum":
        aggregate_field = plan.get("aggregate_field")

        if aggregate_field not in definition.get(
            "aggregate_fields", []
        ):
            raise QueryPlanError("Aggregate field is not allowed.")

        if (
            "group_by_field" in plan
            or "aggregate_function" in plan
        ):
            raise QueryPlanError(
                "sum does not accept grouping options."
            )

    elif operation == "group_by":
        group_by_field = plan.get("group_by_field")

        if group_by_field not in definition.get(
            "group_by_fields", []
        ):
            raise QueryPlanError("Grouping field is not allowed.")

        aggregate_function = plan.get("aggregate_function")

        if aggregate_function not in {"count", "sum"}:
            raise QueryPlanError(
                "aggregate_function must be count or sum."
            )

        if aggregate_function == "sum":
            aggregate_field = plan.get("aggregate_field")

            if aggregate_field not in definition.get(
                "aggregate_fields", []
            ):
                raise QueryPlanError(
                    "Aggregate field is not allowed."
                )

        elif "aggregate_field" in plan:
            raise QueryPlanError(
                "aggregate_field is not allowed for grouped counts."
            )

    elif (
        "aggregate_field" in plan
        or "group_by_field" in plan
        or "aggregate_function" in plan
    ):
        raise QueryPlanError(
            "Aggregation options do not apply to this operation."
        )

    filters = plan.get("filters", {})

    if not isinstance(filters, dict):
        raise QueryPlanError("filters must be an object.")

    if any(
        key not in definition["filters"]
        for key in filters
    ):
        raise QueryPlanError("Filter is not allowed.")
    
        # Resolve approved identity-context filters using trusted
    # authentication data, never model-generated identity values.
    identity_filters = definition.get("identity_filters", {})
    resolved_filters = {}

    for field, value in filters.items():
        if isinstance(value, dict) and "$context" in value:
            expected_context = identity_filters.get(field)

            if (
                expected_context != "employee_id"
                or value != {"$context": expected_context}
            ):
                raise QueryPlanError(
                    "Identity context reference is not allowed."
                )

            resolved_filters[field] = employee_id

        else:
            # Reject unresolved identity placeholders instead of
            # treating them as literal database filter values.
            if (
                field in identity_filters
                and isinstance(value, str)
                and value.strip().lower()
                in {
                    "employee_id",
                    "me",
                    "myself",
                    "my",
                    "current user",
                }
            ):
                raise QueryPlanError(
                    "Identity reference must be normalized "
                    "before query execution."
                )

            resolved_filters[field] = value

    filters = resolved_filters
    print(
    "[TASK FILTER DEBUG]",
    {
        "operation_id": operation_id,
        "authenticated_employee_id": employee_id,
        "organization_id": organization_id,
        "resolved_filters": filters,
    },
)

    if db_engine is None:
        from backend.db import engine as db_engine

    engine = db_engine
    preparer = engine.dialect.identifier_preparer

    quoted_schema = preparer.quote_schema(schema_name)
    quoted_table = preparer.quote(definition["table"])

    params: dict[str, Any] = {}
    conditions: list[str] = []

    # ---------------------------------------------------------
    # PAYROLL: fixed, approved three-table join.
    # Employee and organization scope come from authentication.
    # ---------------------------------------------------------
    if operation_id == "payroll_summary.list":
        if organization_id is None:
            raise QueryPlanError(
                "Authenticated organization ID is required "
                "for payroll queries."
            )

        payroll_field_sql = {
            "period_start": (
                f"pp.{preparer.quote('period_start')}"
            ),
            "period_end": (
                f"pp.{preparer.quote('period_end')}"
            ),
            "gross_amount": (
                f"ps.{preparer.quote('gross_amount')}"
            ),
            "deduction_amount": (
                f"ps.{preparer.quote('deduction_amount')}"
            ),
            "net_amount": (
                f"ps.{preparer.quote('net_amount')}"
            ),
            "currency": (
                f"ps.{preparer.quote('currency')}"
            ),
        }

        if any(
            field not in payroll_field_sql
            for field in requested_fields
        ):
            raise QueryPlanError(
                "Requested payroll field is not allowed."
            )

        payroll_conditions = [
            (
                f"ps.{preparer.quote('employee_id')} "
                "= :authenticated_employee_id"
            ),
            (
                f"e.{preparer.quote('id')} "
                "= :authenticated_employee_id"
            ),
            (
                f"e.{preparer.quote('organization_id')} "
                "= :authenticated_organization_id"
            ),
            (
                f"pp.{preparer.quote('organization_id')} "
                "= :authenticated_organization_id"
            ),
            (
                f"pp.{preparer.quote('id')} "
                f"= ps.{preparer.quote('payroll_period_id')}"
            ),
        ]

        payroll_params: dict[str, Any] = {
            "authenticated_employee_id": employee_id,
            "authenticated_organization_id": organization_id,
            "query_limit": limit,
        }

        for field, value in filters.items():
            if field not in {"period_start", "period_end"}:
                raise QueryPlanError(
                    "Payroll filter is not allowed."
                )

            if (
                not isinstance(value, dict)
                or not value
                or set(value) - {"gte", "lte"}
            ):
                raise QueryPlanError(
                    "Payroll date ranges accept only gte and lte."
                )

            for bound in ("gte", "lte"):
                if bound not in value:
                    continue

                parsed = _parse_date(
                    value[bound],
                    f"{field}.{bound}",
                )

                param_name = f"{field}_{bound}"
                payroll_params[param_name] = parsed

                comparator = ">=" if bound == "gte" else "<="

                # A period should be included if it overlaps the
                # requested window:
                # period_end >= requested start
                # period_start <= requested end
                if field == "period_start" and bound == "gte":
                    filter_column = payroll_field_sql["period_end"]

                elif field == "period_start" and bound == "lte":
                    filter_column = payroll_field_sql["period_start"]

                else:
                    filter_column = payroll_field_sql[field]

                payroll_conditions.append(
                    f"CAST({filter_column} AS DATE) "
                    f"{comparator} :{param_name}"
                )

            if "gte" in value and "lte" in value:
                if (
                    payroll_params[f"{field}_gte"]
                    > payroll_params[f"{field}_lte"]
                ):
                    raise QueryPlanError(
                        "Date range start must not be after end."
                    )

        selected = ", ".join(
            (
                f"{payroll_field_sql[field]} "
                f"AS {preparer.quote(field)}"
            )
            for field in requested_fields
        )

        payroll_sql = (
            f"SELECT {selected} "
            f"FROM {quoted_schema}."
            f"{preparer.quote('payroll_summaries')} ps "
            f"JOIN {quoted_schema}."
            f"{preparer.quote('employees')} e "
            f"ON e.{preparer.quote('id')} "
            f"= ps.{preparer.quote('employee_id')} "
            f"JOIN {quoted_schema}."
            f"{preparer.quote('payroll_periods')} pp "
            f"ON pp.{preparer.quote('id')} "
            f"= ps.{preparer.quote('payroll_period_id')} "
            f"WHERE {' AND '.join(payroll_conditions)} "
            f"ORDER BY pp.{preparer.quote('period_start')} "
            "DESC NULLS LAST "
            "LIMIT :query_limit"
        )

        with engine.connect() as connection:
            payroll_rows = connection.execute(
                text(payroll_sql),
                payroll_params,
            ).mappings().all()

        return {
            "operation_id": operation_id,
            "entity": definition["entity"],
            "operation": operation,
            "data": [
                dict(row)
                for row in payroll_rows
            ],
            "limit": limit,
        }

    # ---------------------------------------------------------
    # HOLIDAYS: scope through the employee's organization calendar.
    # The holidays table has calendar_id, not organization_id.
    # ---------------------------------------------------------
    if operation_id in {"holiday.list", "holiday.count"}:
        if organization_id is None:
            raise QueryPlanError(
                "Authenticated organization ID is required "
                "for holiday queries."
            )

        calendar_table = "holiday_calendars"
        holiday_conditions = [
            "hc.id = h.calendar_id",
            "hc.organization_id = :authenticated_organization_id",
        ]
        holiday_params: dict[str, Any] = {
            "authenticated_organization_id": organization_id,
            "query_limit": limit,
        }

        for field, value in filters.items():
            quoted_field = f"h.{preparer.quote(field)}"

            if isinstance(value, dict):
                if field != "holiday_date":
                    raise QueryPlanError(
                        "Range filters are allowed only on holiday_date."
                    )
                if not value or set(value) - {"gte", "lte"}:
                    raise QueryPlanError(
                        "Date ranges accept only gte and lte."
                    )

                for bound, comparator in (("gte", ">="), ("lte", "<=")):
                    if bound not in value:
                        continue
                    parsed = _parse_date(
                        value[bound], f"{field}.{bound}"
                    )
                    param_name = f"holiday_date_{bound}"
                    holiday_params[param_name] = parsed
                    holiday_conditions.append(
                        f"CAST({quoted_field} AS DATE) "
                        f"{comparator} :{param_name}"
                    )

                if (
                    "gte" in value
                    and "lte" in value
                    and holiday_params["holiday_date_gte"]
                    > holiday_params["holiday_date_lte"]
                ):
                    raise QueryPlanError(
                        "Date range start must not be after end."
                    )
            else:
                if value is None or isinstance(value, (dict, list)):
                    raise QueryPlanError(
                        f"Invalid value for filter {field}."
                    )
                if not isinstance(value, (str, int, float, bool, date, datetime)):
                    raise QueryPlanError(
                        f"Invalid value for filter {field}."
                    )
                if isinstance(value, str) and len(value) > 200:
                    raise QueryPlanError("Filter value is too long.")
                holiday_params[field] = value
                holiday_conditions.append(
                    f"{quoted_field} = :{field}"
                )

        where_sql = " AND ".join(holiday_conditions)

        if operation == "count":
            holiday_sql = (
                f"SELECT COUNT(*) AS record_count "
                f"FROM {quoted_schema}.{preparer.quote('holidays')} h "
                f"JOIN {quoted_schema}.{preparer.quote(calendar_table)} hc "
                f"ON hc.{preparer.quote('id')} = "
                f"h.{preparer.quote('calendar_id')} "
                f"WHERE {where_sql}"
            )
        else:
            selected = ", ".join(
                f"h.{preparer.quote(field)} AS {preparer.quote(field)}"
                for field in requested_fields
            )
            holiday_sql = (
                f"SELECT {selected} "
                f"FROM {quoted_schema}.{preparer.quote('holidays')} h "
                f"JOIN {quoted_schema}.{preparer.quote(calendar_table)} hc "
                f"ON hc.{preparer.quote('id')} = "
                f"h.{preparer.quote('calendar_id')} "
                f"WHERE {where_sql} "
                f"ORDER BY h.{preparer.quote('holiday_date')} "
                "DESC NULLS LAST LIMIT :query_limit"
            )

        with engine.connect() as connection:
            holiday_rows = connection.execute(
                text(holiday_sql), holiday_params
            ).mappings().all()

        if operation == "count":
            holiday_data: Any = {
                "count": int(holiday_rows[0]["record_count"])
            }
        else:
            holiday_data = [dict(row) for row in holiday_rows]

        return {
            "operation_id": operation_id,
            "entity": definition["entity"],
            "operation": operation,
            "data": holiday_data,
            "limit": limit if operation == "list" else None,
        }

    # ---------------------------------------------------------
    # EXISTING GENERIC QUERY PATH FOR OTHER ENTITIES.
    # ---------------------------------------------------------
    
    # ---------------------------------------------------------
    # TASK LIST: join employees twice so the UI receives names
    # instead of employee IDs. Other task operations remain generic.
    # ---------------------------------------------------------
    if operation_id == "task.list":
        if organization_id is None:
            raise QueryPlanError(
                "Authenticated organization ID is required "
                "for task queries."
            )

        task_alias = preparer.quote("t")
        assigned_alias = preparer.quote("assigned")
        manager_alias = preparer.quote("manager")

        task_field_sql = {
            "id": f"{task_alias}.{preparer.quote('id')}",
            "title": f"{task_alias}.{preparer.quote('title')}",
            "project_id": f"{task_alias}.{preparer.quote('project_id')}",
            "task_date": f"{task_alias}.{preparer.quote('task_date')}",
            "description": f"{task_alias}.{preparer.quote('description')}",
            "start_time": f"{task_alias}.{preparer.quote('start_time')}",
            "end_time": f"{task_alias}.{preparer.quote('end_time')}",
            "status": f"{task_alias}.{preparer.quote('status')}",
            "assigned_to_employee_id": (
                f"{assigned_alias}.{preparer.quote('full_name')}"
            ),
            "managed_by_employee_id": (
                f"{manager_alias}.{preparer.quote('full_name')}"
            ),
            "performance_score": (
                f"{task_alias}.{preparer.quote('performance_score')}"
            ),
        }

        if any(field not in task_field_sql for field in requested_fields):
            raise QueryPlanError("Requested task field is not allowed.")

        task_conditions = [
            (
                f"{task_alias}.{preparer.quote('organization_id')} "
                "= :authenticated_organization_id"
            ),
            (
                f"("
                f"{task_alias}.{preparer.quote('assigned_to_employee_id')} "
                "= :authenticated_employee_id OR "
                f"{task_alias}.{preparer.quote('managed_by_employee_id')} "
                "= :authenticated_employee_id"
                f")"
            ),
        ]
        task_params: dict[str, Any] = {
            "authenticated_organization_id": organization_id,
            "authenticated_employee_id": employee_id,
            "query_limit": limit,
        }

        task_date_field = definition.get("date_field")
        task_allowed_date_fields = (
            definition.get("date_fields") or [task_date_field]
        )

        for field, value in filters.items():
            quoted_field = f"{task_alias}.{preparer.quote(field)}"

            if isinstance(value, dict):
                if field not in task_allowed_date_fields:
                    raise QueryPlanError(
                        "Range filters are allowed only "
                        "on the approved task date field."
                    )
                if not value or set(value) - {"gte", "lte"}:
                    raise QueryPlanError(
                        "Date ranges accept only gte and lte."
                    )

                for bound, comparator in (("gte", ">="), ("lte", "<=")):
                    if bound not in value:
                        continue
                    param_name = f"{field}_{bound}"
                    task_params[param_name] = _parse_date(
                        value[bound],
                        f"{field}.{bound}",
                    )
                    task_conditions.append(
                        f"{quoted_field} "
                        f"{comparator} :{param_name}"
                    )

                if (
                    "gte" in value
                    and "lte" in value
                    and task_params[f"{field}_gte"]
                    > task_params[f"{field}_lte"]
                ):
                    raise QueryPlanError(
                        "Date range start must not be after end."
                    )
            else:
                if value is None or isinstance(value, (dict, list)):
                    raise QueryPlanError(
                        f"Invalid value for filter {field}."
                    )
                if isinstance(value, bool):
                    pass
                elif not isinstance(
                    value,
                    (str, int, float, date, datetime),
                ):
                    raise QueryPlanError(
                        f"Invalid value for filter {field}."
                    )
                if isinstance(value, str) and len(value) > 200:
                    raise QueryPlanError("Filter value is too long.")
                if isinstance(value, float):
                    import math
                    if not math.isfinite(value):
                        raise QueryPlanError(
                            "Filter value must be finite."
                        )
                task_params[field] = value
                task_conditions.append(
                    f"{quoted_field} = :{field}"
                )

        selected_task_fields = []
        for field in requested_fields:
            if field == "assigned_to_employee_id":
                expression = task_field_sql[field]
                output_name = "assigned_to"
            elif field == "managed_by_employee_id":
                expression = task_field_sql[field]
                output_name = "managed_by"
            else:
                expression = task_field_sql[field]
                output_name = field

            selected_task_fields.append(
                f"{expression} AS {preparer.quote(output_name)}"
            )

        task_sql = (
            f"SELECT {', '.join(selected_task_fields)} "
            f"FROM {quoted_schema}.{quoted_table} {task_alias} "
            f"LEFT JOIN {quoted_schema}.{preparer.quote('employees')} "
            f"{assigned_alias} "
            f"ON {assigned_alias}.{preparer.quote('id')} = "
            f"{task_alias}.{preparer.quote('assigned_to_employee_id')} "
            f"AND {assigned_alias}.{preparer.quote('organization_id')} = "
            f"{task_alias}.{preparer.quote('organization_id')} "
            f"LEFT JOIN {quoted_schema}.{preparer.quote('employees')} "
            f"{manager_alias} "
            f"ON {manager_alias}.{preparer.quote('id')} = "
            f"{task_alias}.{preparer.quote('managed_by_employee_id')} "
            f"AND {manager_alias}.{preparer.quote('organization_id')} = "
            f"{task_alias}.{preparer.quote('organization_id')} "
            f"WHERE {' AND '.join(task_conditions)} "
            f"ORDER BY {task_alias}.{preparer.quote(task_date_field)} "
            "DESC NULLS LAST "
            "LIMIT :query_limit"
        )

        with engine.connect() as connection:
            task_rows = connection.execute(
                text(task_sql),
                task_params,
            ).mappings().all()

        return {
            "operation_id": operation_id,
            "entity": definition["entity"],
            "operation": operation,
            "data": [dict(row) for row in task_rows],
            "limit": limit,
        }
    
        # ---------------------------------------------------------
    # LOAN REQUEST LIST:
    # Join employees twice to retrieve requester and manager
    # names and employee codes.
    # ---------------------------------------------------------
    if operation_id == "loan_request.list":
        if organization_id is None:
            raise QueryPlanError(
                "Authenticated organization ID is required "
                "for loan request queries."
            )

        loan_alias = preparer.quote("lr")
        employee_alias = preparer.quote("employee")
        manager_alias = preparer.quote("manager")

        loan_field_sql = {
            "id": f"{loan_alias}.{preparer.quote('id')}",
            "employee_id": f"{loan_alias}.{preparer.quote('employee_id')}",
            "managed_by_employee_id": (
                f"{loan_alias}.{preparer.quote('managed_by_employee_id')}"
            ),
            "component": f"{loan_alias}.{preparer.quote('component')}",
            "mode": f"{loan_alias}.{preparer.quote('mode')}",
            "total_amount": f"{loan_alias}.{preparer.quote('total_amount')}",
            "deducted_amount": (
                f"{loan_alias}.{preparer.quote('deducted_amount')}"
            ),
            "remaining_amount": (
                f"{loan_alias}.{preparer.quote('remaining_amount')}"
            ),
            "installment_amount": (
                f"{loan_alias}.{preparer.quote('installment_amount')}"
            ),
            "installments": (
                f"{loan_alias}.{preparer.quote('installments')}"
            ),
            "installments_paid": (
                f"{loan_alias}.{preparer.quote('installments_paid')}"
            ),
            "start_month": f"{loan_alias}.{preparer.quote('start_month')}",
            "next_deduction": (
                f"{loan_alias}.{preparer.quote('next_deduction')}"
            ),
            "remarks": f"{loan_alias}.{preparer.quote('remarks')}",
            "status": f"{loan_alias}.{preparer.quote('status')}",
            "loan_status": f"{loan_alias}.{preparer.quote('loan_status')}",
            "created_at": f"{loan_alias}.{preparer.quote('created_at')}",
        }

        if any(
            field not in loan_field_sql
            for field in requested_fields
        ):
            raise QueryPlanError(
                "Requested loan request field is not allowed."
            )

        loan_conditions = [
            (
                f"{loan_alias}.{preparer.quote('organization_id')} "
                "= :authenticated_organization_id"
            ),
            (
                "("
                f"{loan_alias}.{preparer.quote('employee_id')} "
                "= :authenticated_employee_id "
                "OR "
                f"{loan_alias}.{preparer.quote('managed_by_employee_id')} "
                "= :authenticated_employee_id"
                ")"
            ),
        ]

        loan_params: dict[str, Any] = {
            "authenticated_organization_id": organization_id,
            "authenticated_employee_id": employee_id,
            "query_limit": limit,
        }

        allowed_date_fields = (
            definition.get("date_fields") or []
        )

        for field, value in filters.items():
            quoted_field = (
                f"{loan_alias}.{preparer.quote(field)}"
            )

            if isinstance(value, dict):
                if field not in allowed_date_fields:
                    raise QueryPlanError(
                        "Range filters are allowed only "
                        "on approved loan request date fields."
                    )

                if not value or set(value) - {"gte", "lte"}:
                    raise QueryPlanError(
                        "Date ranges accept only gte and lte."
                    )

                for bound, comparator in (
                    ("gte", ">="),
                    ("lte", "<="),
                ):
                    if bound not in value:
                        continue

                    param_name = f"loan_{field}_{bound}"

                    loan_params[param_name] = _parse_date(
                        value[bound],
                        f"{field}.{bound}",
                    )

                    loan_conditions.append(
                        f"CAST({quoted_field} AS DATE) "
                        f"{comparator} :{param_name}"
                    )

                if (
                    "gte" in value
                    and "lte" in value
                    and loan_params[f"loan_{field}_gte"]
                    > loan_params[f"loan_{field}_lte"]
                ):
                    raise QueryPlanError(
                        "Date range start must not be after end."
                    )

            else:
                if value is None or isinstance(value, (dict, list)):
                    raise QueryPlanError(
                        f"Invalid value for filter {field}."
                    )

                if not isinstance(
                    value,
                    (str, int, float, bool, date, datetime),
                ):
                    raise QueryPlanError(
                        f"Invalid value for filter {field}."
                    )

                if isinstance(value, str) and len(value) > 200:
                    raise QueryPlanError(
                        "Filter value is too long."
                    )

                loan_params[field] = value

                if field == "component" and isinstance(value, str):
                    loan_conditions.append(
                        f"LOWER({quoted_field}) = LOWER(:{field})"
                    )
                else:
                    loan_conditions.append(
                        f"{quoted_field} = :{field}"
                    )

        selected_fields = [
            (
                f"{loan_field_sql[field]} "
                f"AS {preparer.quote(field)}"
            )
            for field in requested_fields
        ]

        # Additional display fields for the frontend.
        selected_fields.extend([
            (
                f"{employee_alias}.{preparer.quote('full_name')} "
                f"AS {preparer.quote('employee_name')}"
            ),
            (
                f"{employee_alias}.{preparer.quote('employee_code')} "
                f"AS {preparer.quote('employee_code')}"
            ),
            (
                f"{manager_alias}.{preparer.quote('full_name')} "
                f"AS {preparer.quote('managed_by_name')}"
            ),
            (
                f"{manager_alias}.{preparer.quote('employee_code')} "
                f"AS {preparer.quote('managed_by_code')}"
            ),
        ])

        loan_sql = (
            f"SELECT {', '.join(selected_fields)} "
            f"FROM {quoted_schema}."
            f"{preparer.quote('loan_requests')} {loan_alias} "

            f"LEFT JOIN {quoted_schema}."
            f"{preparer.quote('employees')} {employee_alias} "

            f"ON {employee_alias}.{preparer.quote('id')} = "
            f"{loan_alias}.{preparer.quote('employee_id')} "

            f"AND {employee_alias}.{preparer.quote('organization_id')} = "
            f"{loan_alias}.{preparer.quote('organization_id')} "

            f"LEFT JOIN {quoted_schema}."
            f"{preparer.quote('employees')} {manager_alias} "

            f"ON {manager_alias}.{preparer.quote('id')} = "
            f"{loan_alias}.{preparer.quote('managed_by_employee_id')} "

            f"AND {manager_alias}.{preparer.quote('organization_id')} = "
            f"{loan_alias}.{preparer.quote('organization_id')} "

            f"WHERE {' AND '.join(loan_conditions)} "

            f"ORDER BY {loan_alias}.{preparer.quote('created_at')} "
            "DESC NULLS LAST "

            "LIMIT :query_limit"
        )

        with engine.connect() as connection:
            loan_rows = connection.execute(
                text(loan_sql),
                loan_params,
            ).mappings().all()

        return {
            "operation_id": operation_id,
            "entity": definition["entity"],
            "operation": operation,
            "data": [dict(row) for row in loan_rows],
            "limit": limit,
        }

        # Enforce access scope using authenticated identity.
    if definition["scope"] == "employee_id":
        conditions.append(
            f"{preparer.quote('employee_id')} "
            "= :authenticated_employee_id"
        )
        params["authenticated_employee_id"] = employee_id

    elif definition["scope"] == "employee_task":
        if organization_id is None:
            raise QueryPlanError(
                "Authenticated organization ID is required "
                "for task queries."
            )

        conditions.append(
            f"{preparer.quote('organization_id')} "
            "= :authenticated_organization_id"
        )
        params["authenticated_organization_id"] = organization_id

        conditions.append(
            "("
            f"{preparer.quote('assigned_to_employee_id')} "
            "= :authenticated_employee_id "
            "OR "
            f"{preparer.quote('managed_by_employee_id')} "
            "= :authenticated_employee_id"
            ")"
        )
        params["authenticated_employee_id"] = employee_id

    elif definition["scope"] == "employee_manager":
        if organization_id is None:
            raise QueryPlanError(
                "Authenticated organization ID is required "
                "for loan request queries."
            )

        conditions.append(
            f"{preparer.quote('organization_id')} "
            "= :authenticated_organization_id"
        )
        params["authenticated_organization_id"] = organization_id

        conditions.append(
            "("
            f"{preparer.quote('employee_id')} "
            "= :authenticated_employee_id "
            "OR "
            f"{preparer.quote('managed_by_employee_id')} "
            "= :authenticated_employee_id"
            ")"
        )
        params["authenticated_employee_id"] = employee_id

    elif definition["scope"] != "global_read":
        raise QueryPlanError("Unknown access scope.")

    date_field = definition.get("date_field")
    allowed_date_fields = (
        definition.get("date_fields") or [date_field]
    )

    for field, value in filters.items():
        quoted_field = preparer.quote(field)
        date_filter_column = (
            quoted_field
            if definition["entity"] == "task"
            else f"CAST({quoted_field} AS DATE)"
        )

        if isinstance(value, dict):
            if field not in allowed_date_fields:
                raise QueryPlanError(
                    "Range filters are allowed only "
                    "on the approved date field."
                )

            if (
                not value
                or set(value) - {"gte", "lte"}
            ):
                raise QueryPlanError(
                    "Date ranges accept only gte and lte."
                )

            if "gte" in value:
                params[f"{field}_gte"] = _parse_date(
                    value["gte"],
                    f"{field}.gte",
                )

                conditions.append(
                    f"{date_filter_column} >= :{field}_gte"
                )

            if "lte" in value:
                params[f"{field}_lte"] = _parse_date(
                    value["lte"],
                    f"{field}.lte",
                )

                conditions.append(
                    f"{date_filter_column} <= :{field}_lte"
                )

            if (
                "gte" in value
                and "lte" in value
                and params[f"{field}_gte"]
                > params[f"{field}_lte"]
            ):
                raise QueryPlanError(
                    "Date range start must not be after end."
                )

        else:
            if (
                value is None
                or isinstance(value, (dict, list))
            ):
                raise QueryPlanError(
                    f"Invalid value for filter {field}."
                )

            if isinstance(value, bool):
                pass

            elif not isinstance(
                value,
                (str, int, float, date, datetime),
            ):
                raise QueryPlanError(
                    f"Invalid value for filter {field}."
                )

            if isinstance(value, str) and len(value) > 200:
                raise QueryPlanError(
                    "Filter value is too long."
                )

            if isinstance(value, float):
                import math

                if not math.isfinite(value):
                    raise QueryPlanError(
                        "Filter value must be finite."
                    )

            params[field] = value
            if (
                definition["entity"] == "loan_request"
                and field == "component"
                and isinstance(value, str)
            ):
                conditions.append(
                    f"LOWER({quoted_field}) = LOWER(:{field})"
                )
            else:
                conditions.append(
                    f"{quoted_field} = :{field}"
                )

    where_sql = (
        " WHERE " + " AND ".join(conditions)
        if conditions
        else ""
    )

    if operation == "count":
        sql = (
            "SELECT COUNT(*) AS record_count "
            f"FROM {quoted_schema}.{quoted_table}"
            f"{where_sql}"
        )

    elif operation == "sum":
        quoted_aggregate = preparer.quote(
            aggregate_field
        )

        record_count_sql = (
            ", COUNT(*) AS record_count "
            if definition["entity"] == "loan_request"
            else ""
        )
        sql = (
            f"SELECT COALESCE(SUM({quoted_aggregate}), 0) "
            f"AS total{record_count_sql}"
            f"FROM {quoted_schema}.{quoted_table}"
            f"{where_sql}"
        )

    elif operation == "group_by":
        quoted_group = preparer.quote(
            group_by_field
        )

        if aggregate_function == "count":
            aggregate_sql = "COUNT(*)"
            result_alias = "record_count"

        else:
            quoted_aggregate = preparer.quote(
                aggregate_field
            )
            aggregate_sql = (
                f"COALESCE(SUM({quoted_aggregate}), 0)"
            )
            result_alias = "total"

        sql = (
            f"SELECT {quoted_group} AS group_value, "
            f"{aggregate_sql} AS {result_alias} "
            f"FROM {quoted_schema}.{quoted_table}"
            f"{where_sql} "
            f"GROUP BY {quoted_group} "
            f"ORDER BY {quoted_group} NULLS LAST "
            "LIMIT :query_limit"
        )

        params["query_limit"] = limit

    else:
        if not requested_fields:
            raise QueryPlanError(
                "No approved fields selected."
            )

        selected = ", ".join(
            preparer.quote(field)
            for field in requested_fields
        )

        sql = (
            f"SELECT {selected} "
            f"FROM {quoted_schema}.{quoted_table}"
            f"{where_sql}"
        )

        if date_field:
            sql += (
                f" ORDER BY {preparer.quote(date_field)} "
                "DESC NULLS LAST"
            )

        sql += " LIMIT :query_limit"
        params["query_limit"] = limit

    with engine.connect() as connection:
        rows = connection.execute(
            text(sql),
            params,
        ).mappings().all()

    if operation == "count":
        data: Any = {
            "count": int(rows[0]["record_count"])
        }

    elif operation == "sum":
        data = {
            "field": aggregate_field,
            "total": rows[0]["total"],
        }
        if definition["entity"] == "loan_request":
            data["record_count"] = int(rows[0]["record_count"])

    else:
        data = [
            dict(row)
            for row in rows
        ]

    return {
        "operation_id": operation_id,
        "entity": definition["entity"],
        "operation": operation,
        "data": data,
        "limit": (
            limit
            if operation in {"list", "group_by"}
            else None
        ),
    }