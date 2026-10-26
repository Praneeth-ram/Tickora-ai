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
) -> dict[str, Any]:
    if not isinstance(schema_name, str) or not _SCHEMA_RE.fullmatch(schema_name):
        raise QueryPlanError("Invalid trusted schema name.")

    if (
        not isinstance(employee_id, int)
        or isinstance(employee_id, bool)
        or employee_id <= 0
    ):
        raise QueryPlanError("Authenticated employee ID is required.")

    if not isinstance(plan, dict):
        raise QueryPlanError("Query plan must be an object.")

    operation_id = plan.get("operation_id")
    if not isinstance(operation_id, str):
        raise QueryPlanError("operation_id is required.")

    registry = build_operation_registry(schema_name)
    definition = registry.get(operation_id)

    if definition is None:
        raise QueryPlanError("Operation is not registered or available.")

    operation = definition["operation"]
    if operation not in {"list", "count", "sum", "group_by"}:
        raise QueryPlanError("Unsupported operation.")

    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= _MAX_LIMIT:
        raise QueryPlanError(f"limit must be between 1 and {_MAX_LIMIT}.")

    # Validate the requested fields for list operations.
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

    if any(field not in definition["fields"] for field in requested_fields):
        raise QueryPlanError("Requested field is not allowed.")

    aggregate_field = None
    group_by_field = None
    aggregate_function = None

    if operation == "sum":
        aggregate_field = plan.get("aggregate_field")
        if aggregate_field not in definition.get("aggregate_fields", []):
            raise QueryPlanError("Aggregate field is not allowed.")

        if "group_by_field" in plan or "aggregate_function" in plan:
            raise QueryPlanError(
                "sum does not accept grouping options."
            )

    elif operation == "group_by":
        group_by_field = plan.get("group_by_field")
        if group_by_field not in definition.get("group_by_fields", []):
            raise QueryPlanError("Grouping field is not allowed.")

        aggregate_function = plan.get("aggregate_function")
        if aggregate_function not in {"count", "sum"}:
            raise QueryPlanError(
                "aggregate_function must be count or sum."
            )

        if aggregate_function == "sum":
            aggregate_field = plan.get("aggregate_field")
            if aggregate_field not in definition.get("aggregate_fields", []):
                raise QueryPlanError("Aggregate field is not allowed.")
        elif "aggregate_field" in plan:
            raise QueryPlanError(
                "aggregate_field is not allowed for grouped counts."
            )

    elif "aggregate_field" in plan or "group_by_field" in plan or "aggregate_function" in plan:
        raise QueryPlanError(
            "Aggregation options do not apply to this operation."
        )

    filters = plan.get("filters", {})
    if not isinstance(filters, dict):
        raise QueryPlanError("filters must be an object.")

    if any(key not in definition["filters"] for key in filters):
        raise QueryPlanError("Filter is not allowed.")

    if db_engine is None:
        from backend.db import engine as db_engine

    engine = db_engine
    preparer = engine.dialect.identifier_preparer

    quoted_schema = preparer.quote_schema(schema_name)
    quoted_table = preparer.quote(definition["table"])

    params: dict[str, Any] = {}
    conditions: list[str] = []

    # The model never supplies the employee scope. It comes from the
    # authenticated request context.
    if definition["scope"] == "employee_id":
        conditions.append(
            f"{preparer.quote('employee_id')} = :authenticated_employee_id"
        )
        params["authenticated_employee_id"] = employee_id
    elif definition["scope"] != "global_read":
        raise QueryPlanError("Unknown access scope.")

    date_field = definition.get("date_field")
    allowed_date_fields = definition.get("date_fields") or [date_field]

    for field, value in filters.items():
        quoted_field = preparer.quote(field)

        if isinstance(value, dict):
            if field not in allowed_date_fields:
                raise QueryPlanError(
                    "Range filters are allowed only on the approved date field."
                )

            if not value or set(value) - {"gte", "lte"}:
                raise QueryPlanError(
                    "Date ranges accept only gte and lte."
                )

            if "gte" in value:
                params[f"{field}_gte"] = _parse_date(
                    value["gte"], f"{field}.gte"
                )
                conditions.append(f"CAST({quoted_field} AS DATE) >= :{field}_gte")

            if "lte" in value:
                params[f"{field}_lte"] = _parse_date(
                    value["lte"], f"{field}.lte"
                )
                conditions.append(f"CAST({quoted_field} AS DATE) <= :{field}_lte")

            if (
                "gte" in value
                and "lte" in value
                and params[f"{field}_gte"] > params[f"{field}_lte"]
            ):
                raise QueryPlanError(
                    "Date range start must not be after end."
                )
        else:
            if value is None or isinstance(value, (dict, list)):
                raise QueryPlanError(f"Invalid value for filter {field}.")

            if isinstance(value, bool):
                pass
            elif not isinstance(value, (str, int, float, date, datetime)):
                raise QueryPlanError(f"Invalid value for filter {field}.")

            if isinstance(value, str) and len(value) > 200:
                raise QueryPlanError("Filter value is too long.")

            if isinstance(value, float) and not __import__("math").isfinite(value):
                raise QueryPlanError("Filter value must be finite.")

            params[field] = value
            conditions.append(f"{quoted_field} = :{field}")

    where_sql = (
        " WHERE " + " AND ".join(conditions)
        if conditions
        else ""
    )

    if operation == "count":
        sql = (
            "SELECT COUNT(*) AS record_count "
            f"FROM {quoted_schema}.{quoted_table}{where_sql}"
        )

    elif operation == "sum":
        quoted_aggregate = preparer.quote(aggregate_field)
        sql = (
            f"SELECT COALESCE(SUM({quoted_aggregate}), 0) AS total "
            f"FROM {quoted_schema}.{quoted_table}{where_sql}"
        )

    elif operation == "group_by":
        quoted_group = preparer.quote(group_by_field)

        if aggregate_function == "count":
            aggregate_sql = "COUNT(*)"
            result_alias = "record_count"
        else:
            quoted_aggregate = preparer.quote(aggregate_field)
            aggregate_sql = f"COALESCE(SUM({quoted_aggregate}), 0)"
            result_alias = "total"

        sql = (
            f"SELECT {quoted_group} AS group_value, "
            f"{aggregate_sql} AS {result_alias} "
            f"FROM {quoted_schema}.{quoted_table}{where_sql} "
            f"GROUP BY {quoted_group} "
            f"ORDER BY {quoted_group} NULLS LAST "
            "LIMIT :query_limit"
        )
        params["query_limit"] = limit

    else:
        if not requested_fields:
            raise QueryPlanError("No approved fields selected.")

        selected = ", ".join(
            preparer.quote(field) for field in requested_fields
        )
        sql = (
            f"SELECT {selected} "
            f"FROM {quoted_schema}.{quoted_table}{where_sql}"
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
            text(sql), params
        ).mappings().all()

    if operation == "count":
        data: Any = {"count": int(rows[0]["record_count"])}
    elif operation == "sum":
        data = {"field": aggregate_field, "total": rows[0]["total"]}
    else:
        data = [dict(row) for row in rows]

    return {
        "operation_id": operation_id,
        "entity": definition["entity"],
        "operation": operation,
        "data": data,
        "limit": limit if operation in {"list", "group_by"} else None,
    }
