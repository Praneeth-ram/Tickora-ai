import os
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo
import httpx
from backend.services.dynamic_query_service import (
    QueryPlanError,
    execute_query_plan,
)
from backend.services.response_formatter import (
    format_attendance,
    format_date,
    format_date_range,
    format_status_badge,
    format_time,
)

MODEL_SERVER_URL = "http://127.0.0.1:8001/predict"
MODEL_TIMEOUT_SECONDS = 60

DEFAULT_TIMEZONE = os.getenv("APP_TIMEZONE", os.getenv("TICKORA_TIMEZONE", "Asia/Kolkata"))

MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

OPERATION_DATE_FIELDS = {
    "attendance.list": "attendance_date",
    "attendance.count": "attendance_date",
    "attendance.sum": "attendance_date",
    "attendance.group_by": "attendance_date",
    "leave_request.list": "start_date",
    "leave_request.count": "start_date",
    "wfh_request.list": "start_date",
    "wfh_request.count": "start_date",
    "timesheet.list": "period_start",
    "timesheet.count": "period_start",
    "holiday.list": "holiday_date",
    "holiday.count": "holiday_date",
}


class ModelServiceError(RuntimeError):
    """Raised when the inference service cannot produce a usable plan."""


def get_current_date() -> date:
    """Get the current date using the configured timezone."""
    try:
        tz = ZoneInfo(DEFAULT_TIMEZONE)
        return datetime.now(tz).date()
    except Exception:
        return date.today()


def get_query_plan(question: str) -> dict[str, Any]:
    """Ask the persistent Qwen service for a structured query plan."""
    try:
        response = httpx.post(
            MODEL_SERVER_URL,
            json={"question": question},
            timeout=MODEL_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ModelServiceError(
            "The Tickora language model is temporarily unavailable."
        ) from exc

    plan = payload.get("plan")
    if not isinstance(plan, dict):
        raise ModelServiceError("The model returned an invalid query plan.")

    return plan


def resolve_date_range_from_question(question: str, today: date) -> tuple[date, date] | None:
    """Resolve relative dates, month names, and explicit dates from the question."""
    q = question.lower()

    # 1. Today
    if re.search(r"\btoday\b", q):
        return today, today

    # 2. Yesterday
    if re.search(r"\byesterday\b", q):
        y = today - timedelta(days=1)
        return y, y

    # 3. This week (Monday to Sunday)
    if re.search(r"\bthis\s+week\b", q):
        start = today - timedelta(days=today.weekday())
        return start, start + timedelta(days=6)

    # 4. Last week
    if re.search(r"\blast\s+week\b", q):
        start = today - timedelta(days=today.weekday() + 7)
        return start, start + timedelta(days=6)

    # 5. This month
    if re.search(r"\bthis\s+month\b", q):
        start = today.replace(day=1)
        next_month = (
            date(today.year + 1, 1, 1)
            if today.month == 12
            else date(today.year, today.month + 1, 1)
        )
        return start, next_month - timedelta(days=1)

    # 6. Last month
    if re.search(r"\blast\s+month\b", q):
        this_month_start = today.replace(day=1)
        last_month_end = this_month_start - timedelta(days=1)
        start = last_month_end.replace(day=1)
        return start, last_month_end

    # 7. ISO range: YYYY-MM-DD to/through/and YYYY-MM-DD
    range_match = re.search(
        r"(\d{4}-\d{2}-\d{2})\s*(?:to|through|and|-)\s*(\d{4}-\d{2}-\d{2})",
        q,
    )
    if range_match:
        try:
            return (
                date.fromisoformat(range_match.group(1)),
                date.fromisoformat(range_match.group(2)),
            )
        except ValueError:
            pass

    # 8. Single ISO date: on YYYY-MM-DD
    single_iso = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", q)
    if single_iso:
        try:
            d = date.fromisoformat(single_iso.group(1))
            return d, d
        except ValueError:
            pass

    # 9. Month Name (e.g. "october 2026", "in october", "oct 2026")
    month_pattern = r"\b(" + "|".join(MONTH_MAP.keys()) + r")\b(?:\s+(20\d\d))?"
    month_match = re.search(month_pattern, q)
    if month_match:
        mo = MONTH_MAP[month_match.group(1)]
        yr = int(month_match.group(2)) if month_match.group(2) else today.year
        start = date(yr, mo, 1)
        next_m = (
            date(yr + 1, 1, 1)
            if mo == 12
            else date(yr, mo + 1, 1)
        )
        return start, next_m - timedelta(days=1)

    # 10. This year / specific 4-digit year (e.g. "in this year 2026", "in this year", "for 2026")
    year_match = re.search(r"\b(?:this\s+year|year\s+(20\d\d)|in\s+(20\d\d)|for\s+(20\d\d))\b", q)
    if year_match or "this year" in q:
        explicit_yr = (
            year_match.group(1) or year_match.group(2) or year_match.group(3)
            if year_match
            else None
        )
        yr = int(explicit_yr) if explicit_yr else today.year
        return date(yr, 1, 1), date(yr, 12, 31)

    # 11. Any standalone 4-digit year like 2026
    standalone_yr = re.search(r"\b(20\d\d)\b", q)
    if standalone_yr:
        yr = int(standalone_yr.group(1))
        return date(yr, 1, 1), date(yr, 12, 31)

    return None


def normalize_and_correct_plan(
    plan: dict[str, Any],
    question: str,
    today: date,
) -> tuple[dict[str, Any], dict[str, str | None]]:
    """
    Enforce backend query accuracy:
    - Distinguish attendance summaries (grouped by status) vs clock-in vs counts vs sums.
    - Resolve relative dates ('this month', 'this year', 'today') using Python.
    - Never trust hallucinated dates from the LLM.
    """
    normalized = dict(plan)
    filters = dict(normalized.get("filters") or {})
    q = question.lower()

    # Determine operation_id
    op_id = normalized.get("operation_id", "")

    # 1. Distinguish Attendance Summary
    is_summary_query = bool(
        re.search(
            r"\b(?:attendance\s+summary|summary\s+of\s+(?:my\s+)?attendance|"
            r"attendance\s+breakdown|breakdown\s+of\s+(?:my\s+)?attendance|"
            r"attendance\s+status(?:es)?\s+overview)\b",
            q,
        )
        or ("attendance" in q and "summary" in q and "timesheet" not in q)
    )
    if is_summary_query:
        op_id = "attendance.group_by"
        normalized["operation_id"] = "attendance.group_by"
        normalized["group_by_field"] = "status"
        normalized["aggregate_function"] = "count"
        normalized.pop("aggregate_field", None)
        normalized.pop("fields", None)

    # 2. Distinguish Clock In / Check In
    is_clock_in_query = bool(
        re.search(
            r"\b(?:clock[- ]in|check[- ]in|punch[- ]in|clock[- ]out|check[- ]out|punch[- ]out)\b",
            q,
        )
    )
    if is_clock_in_query:
        op_id = "attendance.list"
        normalized["operation_id"] = "attendance.list"
        normalized.pop("group_by_field", None)
        normalized.pop("aggregate_function", None)
        normalized.pop("aggregate_field", None)

    # 3. Distinguish Sum queries (worked minutes, overtime)
    is_sum_query = bool(
        re.search(
            r"\b(?:total\s+(?:worked\s+)?(?:minutes|hours|time)|how\s+much\s+overtime|"
            r"total\s+overtime|sum\s+of\s+(?:worked\s+)?minutes|calculate\s+(?:my\s+)?total\s+worked)\b",
            q,
        )
    )
    if is_sum_query and not is_summary_query:
        op_id = "attendance.sum"
        normalized["operation_id"] = "attendance.sum"
        if "overtime" in q:
            normalized["aggregate_field"] = "overtime_minutes"
        else:
            normalized["aggregate_field"] = "worked_minutes"
        normalized.pop("group_by_field", None)
        normalized.pop("aggregate_function", None)
        normalized.pop("fields", None)

    # 4. Distinguish Count queries
    is_count_query = bool(
        re.search(r"\b(?:how\s+many|count|number\s+of)\b", q)
    )
    if is_count_query and not is_summary_query and not is_sum_query:
        if "leave" in q:
            op_id = "leave_request.count"
        elif "wfh" in q or "work from home" in q:
            op_id = "wfh_request.count"
        elif "timesheet" in q:
            op_id = "timesheet.count"
        elif "holiday" in q:
            op_id = "holiday.count"
        elif "attendance" in q or "late" in q or "absent" in q or "present" in q:
            op_id = "attendance.count"

        normalized["operation_id"] = op_id
        normalized.pop("group_by_field", None)
        normalized.pop("aggregate_function", None)
        normalized.pop("aggregate_field", None)
        normalized.pop("fields", None)

    # Status filters
    status_keywords = {
        "late": "late",
        "absent": "absent",
        "present": "present",
        "half day": "half_day",
        "half-day": "half_day",
        "pending": "pending",
        "approved": "approved",
        "rejected": "rejected",
        "cancelled": "cancelled",
        "draft": "draft",
        "submitted": "submitted",
    }
    for word, st_val in status_keywords.items():
        if re.search(r"\b" + re.escape(word) + r"\b", q):
            if op_id in {
                "attendance.list", "attendance.count", "attendance.group_by",
                "leave_request.list", "leave_request.count",
                "wfh_request.list", "wfh_request.count",
                "timesheet.list", "timesheet.count",
            }:
                if not (op_id == "attendance.group_by" and normalized.get("group_by_field") == "status"):
                    filters["status"] = st_val
            break

    # 5. Clean model-generated dates and resolve authoritative Python dates
    date_field = OPERATION_DATE_FIELDS.get(op_id)

    # Strip any dates hallucinated by the model
    for df in ["attendance_date", "start_date", "period_start", "holiday_date", "work_date"]:
        filters.pop(df, None)

    date_range = resolve_date_range_from_question(question, today)

    if date_range is not None and date_field:
        filters[date_field] = {
            "gte": date_range[0].isoformat(),
            "lte": date_range[1].isoformat(),
        }
    elif date_range is None and op_id in {"attendance.list", "attendance.group_by", "attendance.sum"}:
        # Default attendance queries to this month if no period was specified
        start = today.replace(day=1)
        next_month = (
            date(today.year + 1, 1, 1)
            if today.month == 12
            else date(today.year, today.month + 1, 1)
        )
        end = next_month - timedelta(days=1)
        date_range = (start, end)
        filters[date_field] = {
            "gte": start.isoformat(),
            "lte": end.isoformat(),
        }

    # Handle holiday upcoming queries
    if op_id == "holiday.list" and date_range is None:
        if any(phrase in q for phrase in ("coming up", "upcoming", "next holidays", "holidays")):
            start = today
            end = date(today.year, 12, 31)
            date_range = (start, end)
            filters["holiday_date"] = {
                "gte": start.isoformat(),
                "lte": end.isoformat(),
            }

    normalized["filters"] = filters

    resolved_period = {
        "start_date": date_range[0].isoformat() if date_range else None,
        "end_date": date_range[1].isoformat() if date_range else None,
    }

    return normalized, resolved_period


def normalize_result_fields(
    operation_id: str,
    data: Any,
) -> Any:
    """Normalize query results for the existing response formatter."""
    if not isinstance(data, list):
        return data

    aliases_by_operation = {
        "attendance.list": {
            "attendance_date": "work_date",
        },
        "holiday.list": {
            "name": "holiday_name",
        },
        "timesheet.list": {
            "period_start": "work_date",
            "status": "submission_status",
        },
        "leave_request.list": {
            "applied_at": "requested_at",
        },
        "wfh_request.list": {
            "applied_at": "requested_at",
        },
    }

    aliases = aliases_by_operation.get(operation_id, {})
    normalized = []

    for row in data:
        if not isinstance(row, dict):
            normalized.append(row)
            continue

        item = dict(row)

        for source, target in aliases.items():
            if source in item and target not in item:
                item[target] = item[source]

        normalized.append(item)

    return normalized


def format_clock_in_response(data: Any, question: str) -> str:
    """Format clock-in/clock-out queries cleanly."""
    if not isinstance(data, list) or not data:
        return "No clock-in records were found for the requested period."

    lines = [f"Found clock-in record(s) for {len(data)} day(s):"]
    for row in data:
        wdate = format_date(row.get("work_date") or row.get("attendance_date"))
        cin = format_time(row.get("clock_in"))
        cout = format_time(row.get("clock_out"))
        status = format_status_badge(row.get("status"))
        loc = str(row.get("work_location") or "Office").title()
        lines.append(f"- {wdate}: In at {cin} | Out at {cout} | Status: {status} ({loc})")

    return "\n".join(lines)


def format_timesheet_response(data: Any) -> str:
    """Format timesheet periods using fields available in the database."""
    if not isinstance(data, list) or not data:
        return "No matching timesheet records were found."

    lines = [f"Found {len(data)} timesheet record(s):"]

    for row in data:
        start = row.get("period_start", row.get("work_date"))
        end = row.get("period_end")
        status = row.get("status", "unknown")

        if start and end:
            period = f"{start:%d %b %Y} to {end:%d %b %Y}"
        elif start:
            period = f"{start:%d %b %Y}"
        else:
            period = "Period unavailable"

        lines.append(f"- {period} | Status: {str(status).title()}")

    return "\n".join(lines)


def format_request_response(
    data: Any,
    entity_label: str,
) -> str:
    """Format leave or WFH request records using available fields."""
    if not isinstance(data, list) or not data:
        return f"No matching {entity_label} requests were found."

    lines = [
        f"Found {len(data)} {entity_label} request(s):"
    ]

    for row in data:
        start = row.get("start_date")
        end = row.get("end_date")
        status = str(row.get("status", "unknown")).title()
        reason = row.get("reason")
        applied_at = row.get("applied_at", row.get("requested_at"))

        if start and end:
            period = f"{start:%d %b %Y} to {end:%d %b %Y}"
        elif start:
            period = f"{start:%d %b %Y}"
        else:
            period = "Dates unavailable"

        lines.append(f"- {period} | Status: {status}")

        if reason:
            lines.append(f"  Reason: {reason}")

        if applied_at:
            lines.append(f"  Requested: {applied_at:%d %b %Y}")

    return "\n".join(lines)


def run_llm_chat(
    question: str,
    employee_id: int,
) -> dict[str, Any]:
    """Generate a plan, correct it with authoritative Python logic, execute safely, and format the response."""
    today = get_current_date()
    raw_plan = get_query_plan(question)
    plan, period = normalize_and_correct_plan(raw_plan, question, today)

    try:
        query_result = execute_query_plan(
            plan,
            employee_id=employee_id,
        )
    except QueryPlanError as exc:
        raise ModelServiceError(
            f"The query plan failed validation: {exc}"
        ) from exc

    operation_id = query_result["operation_id"]
    operation = query_result["operation"]
    entity = query_result["entity"]

    data = normalize_result_fields(
        operation_id,
        query_result["data"],
    )

    operation_to_intent = {
        "attendance.list": "attendance_records",
        "attendance.count": "attendance_summary",
        "attendance.sum": "attendance_summary",
        "attendance.group_by": "attendance_summary",
        "leave_request.list": "leave_status",
        "leave_request.count": "leave_status",
        "wfh_request.list": "wfh_status",
        "wfh_request.count": "wfh_status",
        "timesheet.list": "timesheet_lookup",
        "timesheet.count": "timesheet_lookup",
        "holiday.list": "holiday_lookup",
        "holiday.count": "holiday_lookup",
    }

    intent = operation_to_intent.get(operation_id, "attendance_records")

    # Handle count operations.
    if operation == "count":
        count = data.get("count", 0) if isinstance(data, dict) else 0

        count_labels = {
            "attendance": "attendance record(s)",
            "leave_request": "leave request(s)",
            "wfh_request": "work-from-home request(s)",
            "timesheet": "timesheet record(s)",
            "holiday": "holiday(s)",
        }

        label = count_labels.get(entity, "record(s)")
        status_filter = plan.get("filters", {}).get("status")
        status_desc = f"{str(status_filter).replace('_', ' ').title()} " if status_filter else ""

        if period.get("start_date") and period.get("end_date"):
            date_ctx = f" for the period {format_date_range(period['start_date'], period['end_date'])}"
        else:
            date_ctx = ""

        answer = f"You have {count} {status_desc}{label}{date_ctx}."

        return {
            "success": True,
            "question": question,
            "answer": answer,
            "message": answer,
            "intent": intent,
            "confidence": None,
            "period": period,
            "show_table": False,
            "raw_data": data,
            "data": data,
        }

    # Handle attendance summary / group_by operations
    if operation_id == "attendance.group_by":
        rows = data if isinstance(data, list) else []

        if not rows:
            answer = "No matching attendance records were found."
        else:
            summaries = []
            total_records = 0

            for row in rows:
                if not isinstance(row, dict):
                    continue

                group_value = str(
                    row.get("group_value", "unknown")
                ).replace("_", " ").title()

                record_count = row.get("record_count", 0)

                if (
                    isinstance(record_count, (int, float))
                    and not isinstance(record_count, bool)
                ):
                    total_records += int(record_count)

                summaries.append(
                    f"{int(record_count)} {group_value.lower()} record(s)"
                )

            if period.get("start_date") and period.get("end_date"):
                date_context = (
                    f"Between {format_date_range(period['start_date'], period['end_date'])}, "
                )
            else:
                date_context = ""

            answer = (
                f"{date_context}you had "
                f"{', '.join(summaries)}, "
                f"for a total of {total_records} attendance records."
            )

        return {
            "success": True,
            "question": question,
            "answer": answer,
            "message": answer,
            "intent": intent,
            "confidence": None,
            "requested_metric": None,
            "requested_field": None,
            "status": None,
            "region": None,
            "period": period,
            "show_table": bool(rows),
            "raw_data": data,
            "data": data,
        }

    # Handle sum operations
    if operation == "sum":
        field = (
            data.get("field", "value")
            if isinstance(data, dict)
            else "value"
        )
        total = data.get("total") if isinstance(data, dict) else None

        if period.get("start_date") and period.get("end_date"):
            date_ctx = f" for the period {format_date_range(period['start_date'], period['end_date'])}"
        else:
            date_ctx = ""

        if (
            field in {"worked_minutes", "overtime_minutes"}
            and isinstance(total, (int, float))
            and not isinstance(total, bool)
        ):
            hours, minutes = divmod(int(total), 60)
            field_name = "worked time" if field == "worked_minutes" else "overtime"
            answer = (
                f"Your total {field_name}{date_ctx} was {hours} hours "
                f"and {minutes} minutes ({int(total):,} minutes)."
            )
        else:
            answer = f"Your total for {field}{date_ctx} was {total}."

        return {
            "success": True,
            "question": question,
            "answer": answer,
            "message": answer,
            "intent": intent,
            "confidence": None,
            "period": period,
            "show_table": False,
            "raw_data": data,
            "data": data,
        }

    # Format list results
    is_clock_in_query = bool(
        re.search(
            r"\b(?:clock[- ]in|check[- ]in|punch[- ]in|clock[- ]out|check[- ]out|punch[- ]out)\b",
            question.lower(),
        )
    )

    if operation_id == "attendance.list":
        if is_clock_in_query:
            message = format_clock_in_response(data, question)
        else:
            message = format_attendance(data, question=question)
    elif operation_id == "timesheet.list":
        message = format_timesheet_response(query_result["data"])
    elif operation_id == "leave_request.list":
        message = format_request_response(query_result["data"], "leave")
    elif operation_id == "wfh_request.list":
        message = format_request_response(query_result["data"], "work-from-home")
    elif isinstance(data, list):
        message = (
            f"Found {len(data)} matching record(s)."
            if data
            else "No matching records were found."
        )
    else:
        message = "Your requested information was retrieved."

    result = {
        "success": True,
        "question": question,
        "answer": message,
        "message": message,
        "intent": intent,
        "confidence": None,
        "requested_metric": None,
        "requested_field": None,
        "status": None,
        "region": None,
        "period": period,
        "show_table": isinstance(data, list) and len(data) > 0,
        "raw_data": data,
        "data": data,
    }

    return result
