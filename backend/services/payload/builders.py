"""Build the small, labelled payload the responder receives.
Fields come only from build_specs() (the registry), so nothing outside the
approved field list reaches the model. Entities that are not narratable raise
PayloadError, and the caller keeps the template answer.
"""
from __future__ import annotations

from datetime import date
from typing import Any

MAX_ROWS = 5
MAX_MONTHS = 3
MINUTE_FIELDS = {"worked_minutes", "overtime_minutes"}

STATUS_LABELS = {
    "present": "present", "absent": "absent", "late": "late",
    "half_day": "half day", "on_leave": "on leave",
    "work_from_home": "work from home", "pending": "pending",
    "approved": "approved", "rejected": "rejected", "cancelled": "cancelled",
    "submitted": "submitted", "draft": "draft", "active": "active",
    "in_progress": "in progress", "completed": "completed",
}

# Field-level visibility beyond entity access. Performance score: managers and
# above only. Change here if the decision changes.
HIDDEN_FROM_ROLES: dict[tuple[str, str], set[str]] = {
    ("task", "performance_score"): {"employee"},
}


class PayloadError(ValueError):
    """The payload cannot be built under the rules. The caller uses the template."""


def period_label(start: date | None, end: date | None) -> str:
    if start is None or end is None:
        return "all dates"
    return f"{start.day} {start:%b %Y} to {end.day} {end:%b %Y}"


def label_value(value: Any) -> Any:
    if isinstance(value, str):
        return STATUS_LABELS.get(value, value.replace("_", " "))
    return value


def clean_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    """Keep plain, labelled filters only. Dates and identity references are left out."""
    out: dict[str, Any] = {}
    for key, value in (filters or {}).items():
        if key in {"status", "loan_status", "is_late", "work_location"} and isinstance(value, (str, bool)):
            out[key] = label_value(value)
    return out


def visible_fields(entity: str, fields: list[str], role: str) -> list[str]:
    return [f for f in fields if role not in HIDDEN_FROM_ROLES.get((entity, f), set())]


def _base(shape: str, spec: dict[str, Any], start: date | None, end: date | None,
          filters: dict[str, Any] | None) -> dict[str, Any]:
    if not spec["narratable"]:
        raise PayloadError(f"{spec['label']} is not narratable")
    return {
        "shape": shape,
        "entity": spec["label"],
        "unit": spec["unit"],
        "period": {"label": period_label(start, end)},
        "filters": clean_filters(filters),
        "error": None,
    }


def build_count(spec, count: int, start, end, filters=None) -> dict[str, Any]:
    p = _base("count", spec, start, end, filters)
    p["result"] = {"count": int(count)}
    return p


def build_sum(spec, field: str, total: Any, start, end, filters=None) -> dict[str, Any]:
    p = _base("sum", spec, start, end, filters)
    if field in MINUTE_FIELDS:
        minutes = int(total or 0)
        hours, remainder = divmod(minutes, 60)
        p["result"] = {
            "hours": hours,
            "minutes": remainder,
            "total_minutes": minutes,
        }
    else:
        p["result"] = {"field": spec["field_labels"].get(field, field), "total": float(total or 0)}
    return p


def build_group_by(spec, rows: list[dict[str, Any]], start, end, filters=None) -> dict[str, Any]:
    p = _base("group_by", spec, start, end, filters)
    groups = []
    for row in rows[:20]:
        value = row.get("group_value")
        label = label_value(value) if value is not None else "not recorded"
        groups.append({"label": label, "count": row.get("record_count", row.get("total", 0))})
    p["result"] = {"groups": groups}
    return p


def build_list_short(spec, entity: str, rows: list[dict[str, Any]], total: int,
                     start, end, role: str, filters=None) -> dict[str, Any]:
    p = _base("list_short", spec, start, end, filters)
    allowed = visible_fields(entity, list(spec["field_labels"]), role)
    shown = [{k: label_value(r.get(k)) for k in allowed if k in r} for r in rows[:MAX_ROWS]]
    p["result"] = {"total": int(total), "shown": len(shown)}
    p["rows"] = shown
    p["truncated"] = int(total) > len(shown)
    return p


def build_single(spec, entity: str, row: dict[str, Any] | None, day: date,
                 role: str) -> dict[str, Any]:
    p = _base("single", spec, day, day, None)
    if row is None:
        p["result"] = {}
        p["found"] = False
        return p
    allowed = visible_fields(entity, list(spec["field_labels"]), role)
    p["result"] = {k: label_value(row.get(k)) for k in allowed if k in row}
    p["found"] = True
    return p


def build_summary(spec, by_status: dict[str, int], by_month: list[dict[str, Any]],
                  start, end, filters=None) -> dict[str, Any]:
    p = _base("summary", spec, start, end, filters)
    p["result"] = {
        "total": sum(by_status.values()),
        "by_status": {label_value(k): v for k, v in by_status.items()},
    }
    p["by_month"] = [
        {"month": m["month"], **{label_value(k): v for k, v in m.items() if k != "month"}}
        for m in by_month[-MAX_MONTHS:]
    ]
    return p