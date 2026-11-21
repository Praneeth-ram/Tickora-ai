from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from backend.services.payload.builders import (
    MINUTE_FIELDS,
    clean_filters,
    label_value,
    visible_fields,
)
from backend.services.request_answer_builder import period_phrase

MAX_FACT_ROWS = 5
NARRATABLE_ENTITIES = {
    "attendance",
    "leave_request",
    "wfh_request",
    "timesheet",
    "holiday",
    "leave_balance",
    "task",
    "leave_type",
}


def _decimal_value(value: Any) -> Decimal | None:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def _is_integral(value: Any) -> bool:
    number = _decimal_value(value)
    return number is not None and number == number.to_integral_value()


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def period_text(period: dict) -> str:
    start = _as_date(period.get("start_date"))
    end = _as_date(period.get("end_date"))
    if start is None or end is None:
        return "on record"
    return period_phrase(start, end).strip()


def _base_facts(shape: str, spec: dict, period: dict, filters: dict) -> dict:
    return {
        "shape": shape,
        "entity": spec["label"],
        "unit": spec["unit"],
        "unit_singular": spec["unit_singular"],
        "period_text": period_text(period),
        "filters": clean_filters(filters),
    }


def _count_facts(spec: dict, period: dict, plan: dict, data: dict) -> dict | None:
    count = data.get("count")
    if not isinstance(count, (int, float)) or isinstance(count, bool):
        return None
    if isinstance(count, float) and not count.is_integer():
        return None
    count = int(count)
    facts = _base_facts("count", spec, period, plan.get("filters") or {})
    facts.update({"count": count, "found": count > 0})
    status = (plan.get("filters") or {}).get("status")
    if status is not None:
        facts["status"] = str(label_value(status))
    return facts


def _minutes_facts(
    spec: dict, period: dict, plan: dict, field: str, data: Any
) -> dict | None:
    if isinstance(data, list):
        minutes = [row.get(field) or 0 for row in data if isinstance(row, dict)]
        if any(
            not isinstance(value, (int, float, Decimal))
            or isinstance(value, bool)
            or not _is_integral(value)
            for value in minutes
        ):
            return None
        total = sum(int(value) for value in minutes)
        found = bool(data)
    elif isinstance(data, dict) and isinstance(data.get("total"), (int, float, Decimal)):
        if isinstance(data["total"], bool) or not _is_integral(data["total"]):
            return None
        total = int(data["total"])
        found = bool(data.get("record_count", total != 0))
    else:
        return None

    hours, minutes = divmod(total, 60)
    facts = _base_facts("sum", spec, period, plan.get("filters") or {})
    facts.update({
        "measure": spec["field_labels"].get(field, field),
        "hours": hours,
        "minutes": minutes,
        "found": found,
    })
    return facts


def _sum_facts(
    spec: dict, period: dict, plan: dict, data: dict, entity: str, role: str
) -> dict | None:
    field = plan.get("aggregate_field") or data.get("field")
    total = data.get("total")
    if (
        field not in spec["field_labels"]
        or field not in visible_fields(entity, [field], role)
    ):
        return None
    if not isinstance(total, (int, float, Decimal)) or isinstance(total, bool):
        return None
    decimal_total = _decimal_value(total)
    if decimal_total is None:
        return None
    if field in MINUTE_FIELDS:
        return _minutes_facts(spec, period, plan, field, data)

    facts = _base_facts("sum", spec, period, plan.get("filters") or {})
    facts.update({
        "measure": spec["field_labels"][field],
        "total": format(decimal_total, "f"),
        "found": bool(data.get("record_count", True)),
    })
    return facts


def _groups_facts(
    spec: dict, entity: str, period: dict, plan: dict, data: list, role: str
) -> dict | None:
    aggregate_function = plan.get("aggregate_function") or "count"
    aggregate_field = plan.get("aggregate_field")
    group_by_field = plan.get("group_by_field")
    if group_by_field not in spec["field_labels"]:
        return None
    if aggregate_function == "sum" and (
        aggregate_field not in spec["field_labels"]
        or aggregate_field not in visible_fields(entity, [aggregate_field], role)
    ):
        return None

    groups = []
    for row in data[:20]:
        if not isinstance(row, dict):
            continue
        count = row.get("record_count", row.get("total", 0))
        if not isinstance(count, (int, float, Decimal)) or isinstance(count, bool):
            continue
        decimal_count = _decimal_value(count)
        if decimal_count is None:
            continue
        value = row.get("group_value")
        group = {"label": label_value(value) if value is not None else "not recorded"}
        if aggregate_function == "sum":
            if aggregate_field in MINUTE_FIELDS:
                hours, minutes = divmod(int(count or 0), 60)
                group.update({"hours": hours, "minutes": minutes})
            else:
                group.update({
                    "measure": spec["field_labels"][aggregate_field],
                    "total": format(Decimal(str(count)), "f"),
                })
        else:
            group["count"] = (
                int(count) if _is_integral(count) else str(count)
            )
        groups.append(group)

    facts = _base_facts("group_by", spec, period, plan.get("filters") or {})
    facts.update({"groups": groups, "found": bool(groups)})
    return facts


def _safe_row(spec: dict, entity: str, row: dict, role: str) -> dict:
    allowed = visible_fields(entity, list(spec["field_labels"]), role)
    result = {}
    for field in allowed:
        if field not in row:
            continue
        value = row[field]
        if value is None or isinstance(value, (dict, list, tuple, set)):
            continue
        if isinstance(value, (date, datetime)):
            value = value.isoformat()
        elif isinstance(value, Decimal):
            value = format(value, "f")
        result[spec["field_labels"][field]] = label_value(value)
    return result


def _single_record_facts(
    spec: dict, entity: str, period: dict, row: dict | None, role: str
) -> dict | None:
    if row is not None and not isinstance(row, dict):
        return None
    record = _safe_row(spec, entity, row, role) if row is not None else {}
    if row is not None and not record:
        return None
    facts = _base_facts("single_record", spec, period, {})
    facts["found"] = row is not None
    facts["record"] = record
    return facts


def _rows_facts(
    spec: dict, entity: str, period: dict, filters: dict, rows: list, role: str
) -> dict | None:
    shown_rows = [
        _safe_row(spec, entity, row, role)
        for row in rows[:MAX_FACT_ROWS]
        if isinstance(row, dict)
    ]
    shown_rows = [row for row in shown_rows if row]
    if rows and not shown_rows:
        return None
    facts = _base_facts("rows", spec, period, filters)
    facts.update({
        "total": len(rows),
        "rows": shown_rows,
        "truncated": len(rows) > len(shown_rows),
        "found": bool(rows),
    })
    return facts


def compute_facts(
    question: str,
    plan: dict,
    period: dict,
    result: dict,
    specs: dict[str, dict] | None = None,
    role: str = "employee",
) -> dict | None:
    operation_id = str(plan.get("operation_id") or "")
    entity, separator, operation = operation_id.rpartition(".")
    spec = (specs or {}).get(entity)
    data = result.get("data")
    if (
        not separator
        or entity not in NARRATABLE_ENTITIES
        or spec is None
        or not spec.get("narratable")
        or spec.get("sensitive")
    ):
        return None

    if operation == "count" and isinstance(data, dict):
        return _count_facts(spec, period, plan, data)
    if operation == "sum":
        field = plan.get("aggregate_field")
        if field in MINUTE_FIELDS:
            return _minutes_facts(spec, period, plan, field, data)
        if isinstance(data, dict):
            return _sum_facts(spec, period, plan, data, entity, role)
        return None
    if operation == "group_by" and isinstance(data, list):
        return _groups_facts(spec, entity, period, plan, data, role)
    if operation == "list" and isinstance(data, list):
        filters = plan.get("filters") or {}
        if plan.get("aggregate_field") in MINUTE_FIELDS:
            return _minutes_facts(spec, period, plan, plan["aggregate_field"], data)
        if len(data) == 1:
            return _single_record_facts(spec, entity, period, data[0], role)
        return _rows_facts(spec, entity, period, filters, data, role)
    return None
