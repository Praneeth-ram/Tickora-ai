import logging
import os
import re
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from backend.services.answer_builder import (
    range_clock_answer,
    range_list_answer,
    range_summary_answer,
    single_day_answer,
    status_list_answer,
    status_records_answer,
    fmt_range,
    
)
from backend.services.date_resolver import InvalidDateError, resolve_date_spec, resolve_discrete_dates
from backend.services.dynamic_query_service import QueryPlanError, execute_query_plan
from backend.services.request_answer_builder import (
    as_date,
    holiday_answer,
    period_phrase,
    request_answer,
    status_check_answer,
)
from backend.services.text_normalizer import correct_typos

logger = logging.getLogger(__name__)

MODEL_SERVER_URL = "http://127.0.0.1:8001/predict"
MODEL_TIMEOUT_SECONDS = 60

DEFAULT_TIMEZONE = os.getenv("APP_TIMEZONE", os.getenv("TICKORA_TIMEZONE", "Asia/Kolkata"))

UNSUPPORTED_MESSAGE = (
    "I can answer questions about your attendance, leave, work-from-home requests, "
    "holidays, and timesheets. Please ask about one of these."
)

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
DEFAULT_MONTH_OPERATIONS = {"attendance.list", "attendance.group_by", "attendance.sum"}
ALL_DATE_FILTER_KEYS = {
    "attendance_date", "start_date", "end_date", "period_start", "period_end",
    "holiday_date", "work_date", "applied_at", "requested_at", "submitted_at", "approved_at",
}
APPLIED_RE = re.compile(r"\b(?:appl(?:y|ied|ying|ication)|requested|submitted)\b")
UPCOMING_RE = re.compile(r"\b(?:upcoming|coming\s+up|next|remaining|future)\b")
ATTENDANCE_FIELDS = ["attendance_date", "clock_in", "clock_out", "status", "work_location", "worked_minutes", "overtime_minutes"]
WORK_LOCATION_RE = re.compile(
    r"\b(?:work\s+location|working\s+location|"
    r"where\s+(?:did|do|was|am)\s+i\s+work|"
    r"where\s+was\s+i\s+working)\b",
    re.IGNORECASE,
)
WORK_LOCATION_FIELDS = ["attendance_date", "work_location"]
SUM_QUESTION_RE = re.compile(
    r"\b(?:total\s+(?:worked\s+)?(?:minutes|hours|time)|how\s+much\s+overtime|"
    r"total\s+overtime|sum\s+of\s+(?:worked\s+)?minutes|calculate\s+(?:my\s+)?total\s+worked|"
    r"how\s+many\s+(?:hours|minutes)|hours\s+(?:did\s+i\s+|i\s+)?(?:have\s+)?work(?:ed)?|"
    r"worked\s+hours|working\s+hours)\b"
)
THIRD_PARTY_MESSAGE = (
    "I can only show your own records. I can't access another employee's attendance, "
    "leave, or other details."
)
ATTENDED_STATUSES = {"PRESENT": "present", "LATE": "late", "HALF_DAY": "half day"}
ATTENDED_RE = re.compile(
    r"\b(?:attended|attend|attending|present\s+days?|days?\s+(?:i\s+)?(?:attend|attended|was\s+present)|"
    r"worked\s+days?)\b"
)
SUBMITTED_DATE_RE = re.compile(r"\bsubmitted\s+(?:at|on)\b")
TIMESHEET_RE = re.compile(r"\btimesheets?\b")
TIMESHEET_STATUS_Q_RE = re.compile(
    r"\bstatus\b|\b(?:latest|most\s+recent|recent|current)\b|\blast\s+timesheet\b|"
    r"\b(?:submitted|approved)\s+(?:at|on)\b"
)
TIMESHEET_VERB = {"approved": "was", "rejected": "was", "submitted": "was", "draft": "is"}
_POSSESSIVE_RE = re.compile(r"\b([a-z]+)'s\b")
_SELF_POSSESSIVE_EXCLUSIONS = {
    "what", "that", "it", "there", "here", "who", "let", "this", "he", "she",
    "today", "time", "day", "month", "year", "week",
}
_THIRD_PARTY_WORDS_RE = re.compile(
    r"\b(?:his|her|their|someone|somebody|colleague|colleagues|team|manager|employee|employees|another\s+employee)\b"
)


class ModelServiceError(RuntimeError):
    """Raised when a question cannot be answered from the query plan."""


class ModelUnavailableError(ModelServiceError):
    """The model server cannot be reached or timed out."""


class PlanRejectedError(ModelServiceError):
    """The model server responded, but could not turn the question into a supported plan."""


def get_current_date() -> date:
    try:
        return datetime.now(ZoneInfo(DEFAULT_TIMEZONE)).date()
    except Exception:
        return date.today()


def get_query_plan(question: str) -> dict[str, Any]:
    """Ask the model server for a query plan, keeping outages and rejections distinct."""
    try:
        response = httpx.post(MODEL_SERVER_URL, json={"question": question}, timeout=MODEL_TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        raise ModelUnavailableError("The Tickora language model is temporarily unavailable.") from exc

    if response.status_code == 422:
        raise PlanRejectedError("I couldn't turn that question into a supported query.")
    if response.status_code >= 400:
        raise ModelUnavailableError("The Tickora language model is temporarily unavailable.")

    try:
        payload = response.json()
    except ValueError as exc:
        raise ModelUnavailableError("The Tickora language model returned an unreadable response.") from exc

    plan = payload.get("plan")
    if not isinstance(plan, dict):
        raise PlanRejectedError("I couldn't turn that question into a supported query.")
    return plan


_HOLIDAY_RE = re.compile(r"\bholidays?\b")
_WFH_RE = re.compile(r"\bwfh\b|\bwork\s+from\s+home\b")
_LEAVE_RE = re.compile(r"\bleaves?\b")
_ATTENDANCE_RE = re.compile(
    r"\battendance\b|\bclock\b|\bcheck[- ]?(?:in|out)\b|\bpunch\b|\bstatus\b|\blate\b|"
    r"\babsent\b|\bpresent\b|\bhalf[- ]day\b|\bovertime\b|\bworked\b|\bhours\b"
)
_COUNT_RE = re.compile(r"\bhow\s+many\b|\bcount\b|\bnumber\s+of\b")


def rule_based_plan(question: str) -> dict[str, Any]:
    """Choose the entity from keywords when the model cannot. Dates and filters are still set in code."""
    q = question.lower()
    suffix = ".count" if _COUNT_RE.search(q) else ".list"
    if _HOLIDAY_RE.search(q):
        entity = "holiday"
    elif _WFH_RE.search(q):
        entity = "wfh_request"
    elif _LEAVE_RE.search(q):
        entity = "leave_request"
    elif _ATTENDANCE_RE.search(q):
        entity = "attendance"
    else:
        return {"operation_id": None, "filters": {}}
    return {"operation_id": entity + suffix, "filters": {}}


_DOMAIN_RE = re.compile(
    r"\b(?:leaves?|wfh|work\s+from\s+home|holidays?|attendance|clock|check\s*(?:in|out)|"
    r"status|late|absent|present|timesheets?|applied)\b"
)

def _primary_topic(part: str) -> str | None:
    q = part.lower()
    if _WFH_RE.search(q):
        return "wfh"
    if _LEAVE_RE.search(q):
        return "leave"
    if _HOLIDAY_RE.search(q):
        return "holiday"
    if _ATTENDANCE_RE.search(q) or re.search(r"\b(?:clock|check|punch|attend)", q):
        return "attendance"
    return None


def split_compound_question(question: str) -> list[str]:
    """Split only when the parts are about different topics, e.g. leave and holidays.

    'clock in and clock out' stays one question: both parts are attendance.
    """
    parts = [
        part.strip(" ?.!")
        for part in re.split(r"\s+(?:and|also|plus)\s+|[?;]\s*", question, flags=re.IGNORECASE)
    ]
    parts = [part for part in parts if part]
    if len(parts) > 1:
        topics = [_primary_topic(part) for part in parts]
        if all(topics) and len(set(topics)) > 1:
            return parts
    return [question]

def resolve_date_range_from_question(question: str, today: date) -> tuple[date, date] | None:
    spec = resolve_date_spec(question, today)
    if spec is None:
        return None
    return spec.start, spec.end

ALLOWED_FILTERS = {
    "attendance": {"status", "is_late", "work_location"},
    "leave_request": {"status"},
    "wfh_request": {"status"},
    "timesheet": {"status"},
    "holiday": {"holiday_type"},
}

def question_kind(question: str) -> str:
    q = question.lower()
    asks_in = bool(re.search(r"\b(?:clock[- ]?in|check[- ]?in|punch[- ]?in)\b", q))
    asks_out = bool(re.search(r"\b(?:clock[- ]?out|check[- ]?out|punch[- ]?out)\b", q))
    if asks_in and asks_out:
        return "clock_both"
    if asks_out:
        return "clock_out"
    if asks_in:
        return "clock_in"
    if re.search(r"\bstatus\b", q):
        return "status"
    return "list"

def question_wants_list(question: str) -> bool:
    """Detect requests for records or date-by-date results."""
    return bool(re.search(
        r"\b(?:show|list|all|details?|every|each|table|breakdown|"
        r"day[- ]by[- ]day|which\s+days?|which\s+dates?|"
        r"what\s+dates?|when\s+did\s+i)\b",
        question.lower(),
    ))


def _last_day_of_month(d: date) -> date:
    nxt = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    return nxt - timedelta(days=1)


def normalize_and_correct_plan(
    plan: dict[str, Any],
    question: str,
    today: date,
) -> tuple[dict[str, Any], dict[str, str | None]]:
    """Correct the model's plan with code: operation, status, and every date."""
    normalized = dict(plan)
    q = question.lower()
    op_id = normalized.get("operation_id", "")
        # Work-location questions always use attendance records.
    # This is independent of the requested date or date range.
    asks_work_location = bool(WORK_LOCATION_RE.search(q))

    if asks_work_location:
        op_id = "attendance.list"
        normalized["operation_id"] = op_id

        for key in (
            "group_by_field",
            "aggregate_function",
            "aggregate_field",
        ):
            normalized.pop(key, None)

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
        normalized.update({"operation_id": op_id, "group_by_field": "status", "aggregate_function": "count"})
        normalized.pop("aggregate_field", None)
        normalized.pop("fields", None)

    is_clock_query = bool(re.search(
        r"\b(?:clock[- ]in|check[- ]in|punch[- ]in|clock[- ]out|check[- ]out|punch[- ]out)\b", q
    ))
    is_status_query = bool(re.search(r"\bstatus\b", q)) and not re.search(
        r"\b(?:leave|wfh|work from home|timesheet|holiday)\b", q
    )
    if (is_clock_query or is_status_query) and not is_summary_query:
        op_id = "attendance.list"
        normalized["operation_id"] = op_id
        for key in ("group_by_field", "aggregate_function", "aggregate_field"):
            normalized.pop(key, None)

    is_attended_query = bool(ATTENDED_RE.search(q)) and not is_summary_query
    if is_attended_query:
        op_id = "attendance.list"
        normalized["operation_id"] = op_id
        for key in ("group_by_field", "aggregate_function", "aggregate_field", "fields"):
            normalized.pop(key, None)

    is_sum_query = bool(SUM_QUESTION_RE.search(q))
    if is_sum_query and not is_summary_query:
        op_id = "attendance.list"
        normalized["operation_id"] = op_id
        normalized["aggregate_field"] = "overtime_minutes" if "overtime" in q else "worked_minutes"
        for key in ("group_by_field", "aggregate_function", "fields"):
            normalized.pop(key, None)

    is_count_query = bool(re.search(r"\b(?:how\s+many|count|number\s+of)\b", q))
    if is_count_query and not is_summary_query and not is_sum_query and not is_attended_query:
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
        for key in ("group_by_field", "aggregate_function", "aggregate_field", "fields"):
            normalized.pop(key, None)

    entity = op_id.split(".")[0] if op_id else ""
    allowed_filters = ALLOWED_FILTERS.get(entity, set())
    filters = {
        key: value
        for key, value in (normalized.get("filters") or {}).items()
        if key in allowed_filters and key not in ALL_DATE_FILTER_KEYS and not isinstance(value, dict)
    }

    valid_statuses_by_entity = {
        "attendance": {"present", "late", "absent", "half_day", "on_leave", "work_from_home"},
        "leave_request": {"pending", "approved", "rejected", "cancelled"},
        "wfh_request": {"pending", "approved", "rejected", "cancelled"},
        "timesheet": {"draft", "submitted", "approved", "rejected"},
    }
    status_keywords = {
        "late": "late", "absent": "absent", "present": "present",
        "half day": "half_day", "half-day": "half_day", "pending": "pending",
        "approved": "approved", "rejected": "rejected", "cancelled": "cancelled",
        "draft": "draft", "submitted": "submitted",
    }

    explicit_status = None
    for word, status_value in status_keywords.items():
        if word == "submitted" and SUBMITTED_DATE_RE.search(q):
            continue
        if re.search(r"\b" + re.escape(word) + r"\b", q):
            explicit_status = status_value
            break

    if explicit_status:
        if op_id in {
            "attendance.list", "attendance.count", "attendance.group_by",
            "leave_request.list", "leave_request.count",
            "wfh_request.list", "wfh_request.count",
            "timesheet.list", "timesheet.count",
        } and not (op_id == "attendance.group_by" and normalized.get("group_by_field") == "status"):
            filters["status"] = explicit_status
    else:
        # If the user didn't name a specific status (e.g. asking "what is the status of my leave request?"),
        # do not filter by status; remove any model-hallucinated status filter like "your_status".
        filters.pop("status", None)

    # Validate that any remaining status filter is allowed for this entity
    entity_statuses = valid_statuses_by_entity.get(entity)
    if entity_statuses and filters.get("status") not in entity_statuses:
        filters.pop("status", None)

    if is_attended_query:
        filters.pop("status", None)

    date_field = OPERATION_DATE_FIELDS.get(op_id)
    if op_id.startswith("timesheet.") and SUBMITTED_DATE_RE.search(q):
        date_field = "submitted_at"
    if date_field and op_id.startswith(("leave_request.", "wfh_request.")) and APPLIED_RE.search(q):
        date_field = "applied_at"

    date_range = resolve_date_range_from_question(question, today)
    if date_range is not None:
        if UPCOMING_RE.search(q) and date_field:
            if date_range[0] < today:
                date_range = (today, date_range[1])
        if date_field:
            filters[date_field] = {"gte": date_range[0].isoformat(), "lte": date_range[1].isoformat()}
    elif date_range is None and op_id in DEFAULT_MONTH_OPERATIONS:
        start = today.replace(day=1)
        end = _last_day_of_month(start)
        date_range = (start, end)
        filters[date_field] = {"gte": start.isoformat(), "lte": end.isoformat()}
    elif (
        date_range is None
        and op_id.startswith(("leave_request.", "wfh_request."))
        and UPCOMING_RE.search(q)
    ):
        filters["start_date"] = {"gte": today.isoformat()}
        date_range = (today, date(today.year, 12, 31))
    elif date_range is None and op_id == "holiday.list":
        if UPCOMING_RE.search(q):
            date_range = (today, date(today.year, 12, 31))
        else:
            date_range = (date(today.year, 1, 1), date(today.year, 12, 31))
        filters["holiday_date"] = {"gte": date_range[0].isoformat(), "lte": date_range[1].isoformat()}

    # Ranges longer than 31 days would be truncated in the list, so use the aggregate operations.
    if op_id == "attendance.list" and (is_attended_query or is_sum_query) and date_range is not None:
        if (date_range[1] - date_range[0]).days + 1 > 31:
            if is_attended_query:
                normalized.update({"operation_id": "attendance.group_by", "group_by_field": "status",
                                   "aggregate_function": "count"})
            else:
                normalized.update({"operation_id": "attendance.sum",
                                   "aggregate_field": "overtime_minutes" if "overtime" in q else "worked_minutes"})

    normalized["filters"] = filters
    period = {
        "start_date": date_range[0].isoformat() if date_range else None,
        "end_date": date_range[1].isoformat() if date_range else None,
    }
    return normalized, period


def normalize_result_fields(operation_id: str, data: Any) -> Any:
    if not isinstance(data, list):
        return data

    aliases_by_operation = {
        "attendance.list": {"attendance_date": "work_date"},
        "holiday.list": {"name": "holiday_name"},
        "timesheet.list": {"period_start": "work_date", "status": "submission_status"},
        "leave_request.list": {"applied_at": "requested_at"},
        "wfh_request.list": {"applied_at": "requested_at"},
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


def format_timesheet_response(data: Any) -> str:
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


def _text_result(question: str, answer: str, intent: str) -> dict[str, Any]:
    return {
        "success": True,
        "question": question,
        "answer": answer,
        "message": answer,
        "intent": intent,
        "confidence": None,
        "period": {"start_date": None, "end_date": None},
        "show_table": False,
        "raw_data": None,
        "data": [],
    }


def _result(question: str, answer: str, intent: str, period: dict[str, Any], show_table: bool, data: list) -> dict[str, Any]:
    return {
        "success": True,
        "question": question,
        "answer": answer,
        "message": answer,
        "intent": intent,
        "confidence": None,
        "period": period,
        "show_table": show_table,
        "raw_data": None,
        "data": data if show_table else [],
    }


def _execute(plan: dict[str, Any], employee_id: int, limit: int) -> Any:
    try:
        return execute_query_plan(plan, employee_id=employee_id, limit=limit)
    except QueryPlanError as exc:
        raise ModelServiceError(f"The query plan failed validation: {exc}") from exc


def _attended_sentence(rows, span):
    counts = Counter(
        str(row.get("status") or "").upper()
        for row in rows
        if str(row.get("status") or "").upper() in ATTENDED_STATUSES
    )
    total = sum(counts.values())
    detail = ", ".join(f"{count} {ATTENDED_STATUSES[status]}" for status, count in counts.items())
    noun = "day" if total == 1 else "days"
    where = f" {span}" if span else ""
    return f"You attended {total} {noun}{where}" + (f" ({detail})." if detail else ".")

def _daily_working_hours_answer(rows, requested_dates, tz):
    lines = []
    for day in requested_dates:
        row = next(
            (
                r for r in rows
                if (r.get("attendance_date") or r.get("work_date")) == day
            ),
            None,
        )
        if row is None:
            lines.append(
                f"- {day.day} {day:%B %Y}: no attendance record."
            )
            continue
        minutes = row.get("worked_minutes")
        if minutes is None:
            cin = row.get("clock_in")
            cout = row.get("clock_out")
            if not isinstance(cin, datetime) or not isinstance(cout, datetime):
                lines.append(
                    f"- {day.day} {day:%B %Y}: working hours unavailable."
                )
                continue
            if cin.tzinfo is not None:
                cin = cin.astimezone(tz)
            if cout.tzinfo is not None:
                cout = cout.astimezone(tz)
            minutes = int((cout - cin).total_seconds() // 60)
        hours, remainder = divmod(int(minutes), 60)
        lines.append(
            f"- {day.day} {day:%B %Y}: {hours} hours "
            f"and {remainder} minutes."
        )
    return "Your working hours for the requested dates:\\n" + "\\n".join(lines)

def _hours_sentence(rows, span, overtime):
    field = "overtime_minutes" if overtime else "worked_minutes"
    total = sum(int(row.get(field) or 0) for row in rows)
    hours, minutes = divmod(total, 60)
    name = "overtime" if overtime else "worked time"
    where = f" {span}" if span else ""
    return f"Your total {name}{where} was {hours} hours and {minutes} minutes ({total:,} minutes)."

def _work_location_answer(rows, requested_dates=None):
    """Return only work locations for the requested dates or rows."""
    def row_date(row):
        value = row.get("attendance_date") or row.get("work_date")

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

    def location_for(day):
        row = next((r for r in rows if row_date(r) == day), None)

        if row is None:
            return "no attendance record found"

        location = row.get("work_location")

        if location is None or not str(location).strip():
            return "work location not recorded"

        return str(location).replace("_", " ").strip().title()

    if requested_dates:
        if len(requested_dates) == 1:
            day = requested_dates[0]
            location = location_for(day)
            day_label = f"{day.day} {day:%B %Y}"

            if location == "no attendance record found":
                return (
                    f"I couldn't find an attendance record for "
                    f"{day_label}, so I couldn't verify "
                    "your work location."
                )

            if location == "work location not recorded":
                return (
                    f"Your work location for {day_label} "
                    "has not been recorded."
                )

            return (
                f"You worked from {location} on "
                f"{day_label}."
            )

        lines = []
        for day in requested_dates:
            day_label = f"{day.day} {day:%B %Y}"
            location = location_for(day)

            if location == "no attendance record found":
                detail = "no attendance record found"
            elif location == "work location not recorded":
                detail = "work location not recorded"
            else:
                detail = f"you worked from {location}"

            lines.append(
                f"On {day_label}, {detail}."
            )

        return "\n".join(lines)

    if not rows:
        return "No attendance records were found for the requested period."

    if len(rows) == 1:
        row = rows[0]
        day = row_date(row)
        day_label = f"{day.day} {day:%B %Y}" if day else "the requested date"
        location = row.get("work_location")
        if location is None or not str(location).strip():
            return f"Your work location for {day_label} has not been recorded."
        loc = str(location).replace("_", " ").strip().title()
        return f"You worked from {loc} on {day_label}."

    lines = []
    for row in rows:
        day = row_date(row)
        label = (
            f"{day.day} {day:%B %Y}"
            if day
            else "Date unavailable"
        )
        location = row.get("work_location")

        if location is None or not str(location).strip():
            lines.append(f"On {label}, your work location was not recorded.")
        else:
            loc = str(location).replace("_", " ").strip().title()
            lines.append(f"On {label}, you worked from {loc}.")

    return "\n".join(lines)

def _answer_attendance(question, normalized_question, plan, period, employee_id):
    tz = ZoneInfo(DEFAULT_TIMEZONE)
    kind = question_kind(normalized_question)
    wants_list = question_wants_list(normalized_question)
    start = date.fromisoformat(period["start_date"])
    end = date.fromisoformat(period["end_date"])
    is_single_day = start == end
    discrete_dates = resolve_discrete_dates(normalized_question, get_current_date())
    asks_work_location = bool(
        WORK_LOCATION_RE.search(normalized_question)
    )

    # A list of separately named dates is not a continuous range. Query each
    # requested date independently so dates between them are never returned.
    if discrete_dates:
        requested_rows = []
        for requested_day in discrete_dates:
            one_day_result = _execute(
                {"operation_id": "attendance.list", "filters": {
                    "attendance_date": {"gte": requested_day.isoformat(), "lte": requested_day.isoformat()}
                }, "fields": (
                    WORK_LOCATION_FIELDS
                    if asks_work_location
                    else ATTENDANCE_FIELDS
                )},
                employee_id,
                limit=5,
            )
            day_rows = normalize_result_fields("attendance.list", one_day_result["data"])
            row = day_rows[0] if day_rows else None
            requested_rows.extend(day_rows)
        q_lower = normalized_question.lower()
        if asks_work_location:
            answer = _work_location_answer(
                requested_rows,
                discrete_dates,
            )
            return _result(
                question,
                answer,
                "work_location",
                {
                    "start_date": discrete_dates[0].isoformat(),
                    "end_date": discrete_dates[-1].isoformat(),
                },
                False,
                [],
            )
        asks_working_hours = bool(re.search(
            r"\b(?:working|worked)\s+hours?\b|\btotal\s+worked\s+time\b",
            q_lower,
        ))
        asks_if_late = bool(re.search(
            r"\b(?:was|were|am|did)\s+i\b.{0,40}\b(?:late|arrive\s+late)\b",
            q_lower,
        ))

        def row_for_day(requested_day):
            for item in requested_rows:
                value = item.get("attendance_date") or item.get("work_date")
                if isinstance(value, str):
                    try:
                        value = date.fromisoformat(value[:10])
                    except ValueError:
                        continue
                if value == requested_day:
                    return item
            return None

        if asks_working_hours:
            answer = _daily_working_hours_answer(requested_rows, discrete_dates, tz)
        elif asks_if_late:
            lines = []
            for requested_day in discrete_dates:
                row = row_for_day(requested_day)
                day_label = f"{requested_day.day} {requested_day:%B %Y}"
                if row is None:
                    lines.append(
                        f"I couldn't verify whether you were late on {day_label}, "
                        "because no attendance record was found."
                    )
                elif (
                    str(row.get("status") or "").upper() == "LATE"
                    or row.get("is_late") is True
                ):
                    lines.append(f"Yes, you were marked late on {day_label}.")
                else:
                    lines.append(f"No, you were not marked late on {day_label}.")
            answer = "\n".join(lines)
        elif kind in {"clock_in", "clock_out", "clock_both"}:
            answer = "\n".join(
                single_day_answer(kind, requested_day, row_for_day(requested_day), tz)
                for requested_day in discrete_dates
            )
        else:
            answer = "\n".join(
                single_day_answer("status", requested_day, row_for_day(requested_day), tz)
                for requested_day in discrete_dates
            )
        return _result(question, answer, "attendance_records",
            {"start_date": discrete_dates[0].isoformat(), "end_date": discrete_dates[-1].isoformat()},
            False, [])

    filters: dict[str, Any] = {"attendance_date": {"gte": start.isoformat(), "lte": end.isoformat()}}
    if not is_single_day and plan.get("filters", {}).get("status"):
        filters["status"] = plan["filters"]["status"]

    result = _execute(
        {
            "operation_id": "attendance.list",
            "filters": filters,
            "fields": (
                WORK_LOCATION_FIELDS
                if asks_work_location
                else ATTENDANCE_FIELDS
            ),
        },
        employee_id,
        limit=5 if is_single_day else 100,
    )
    rows = normalize_result_fields("attendance.list", result["data"])
    period_out = {"start_date": start.isoformat(), "end_date": end.isoformat()}
    q = normalized_question.lower()
    
    if asks_work_location:
        answer = _work_location_answer(rows, [start] if is_single_day else None)

        return _result(
            question,
            answer,
            "work_location",
            period_out,
            False,
            [],
        )

    asks_if_late = bool(
        re.search(
            r"\b(?:was|were|am|did)\s+i\b.{0,40}\b(?:late|arrive\s+late)\b",
            q,
        )
    )

    if asks_if_late and is_single_day:
        row = rows[0] if rows else None
        if row is None:
            answer = (
                f"I couldn't verify whether you were late on "
                f"{start.day} {start:%B %Y}, because no attendance "
                f"record was found."
            )
        else:
            late = (
                str(row.get("status") or "").upper() == "LATE"
                or row.get("is_late") is True
            )
            if late:
                answer = (
                    f"Yes, you were marked late on "
                    f"{start.day} {start:%B %Y}."
                )
            else:
                answer = (
                    f"No, you were not marked late on "
                    f"{start.day} {start:%B %Y}."
                )

        return _result(
            question, answer, "attendance_records",
            period_out, False, [],
        )
    span = period_phrase(start, end)

    if ATTENDED_RE.search(normalized_question.lower()):
        return _result(question, _attended_sentence(rows, span), "attendance_summary",
                       period_out, False, [])
    if SUM_QUESTION_RE.search(normalized_question.lower()):
        return _result(question, _hours_sentence(rows, span, "overtime" in normalized_question.lower()),
                       "attendance_summary", period_out, False, [])

    # Status-filtered questions (e.g. "late") list only matching records.
    status_filter = filters.get("status")
    if not is_single_day and status_filter:
        label = str(status_filter).replace("_", " ").lower()
        if wants_list:
            answer = status_list_answer(rows, start, end, label, tz)
            show_table = bool(rows)
            return _result(question, answer, "attendance_records", period_out, show_table, rows)
        answer = status_records_answer(rows, span, label)
        return _result(question, answer, "attendance_records", period_out, False, [])

    if is_single_day:
        answer_kind = kind if kind in {"clock_in", "clock_out", "clock_both"} else "status"
        answer = single_day_answer(answer_kind, start, rows[0] if rows else None, tz)
        show_table = False
    elif kind in {"clock_in", "clock_out", "clock_both"}:
        answer = range_clock_answer(rows, start, end, kind, tz)
        show_table = wants_list and bool(rows)
    elif wants_list:
        answer = range_list_answer(rows, start, end, tz)
        show_table = bool(rows)
    else:
        answer = range_summary_answer(rows, start, end)
        show_table = False

    return _result(question, answer, "attendance_records", period_out, show_table, rows)


def _answer_requests(question, normalized_question, plan, period, employee_id):
    operation_id = plan["operation_id"]
    kind = "leave" if operation_id.startswith("leave_") else "wfh"
    intent = "leave_status" if kind == "leave" else "wfh_status"
    wants_list = (
        question_wants_list(normalized_question)
        or bool(UPCOMING_RE.search(normalized_question.lower()))
    )

    result = _execute(
        {"operation_id": operation_id, "filters": dict(plan.get("filters", {}))},
        employee_id,
        limit=100,
    )
    rows = normalize_result_fields(operation_id, result["data"])
    start, end = as_date(period.get("start_date")), as_date(period.get("end_date"))
    span = period_phrase(start, end)
    answer = request_answer(kind, rows, normalized_question, span, wants_list)
    show_table = wants_list and bool(rows)
    return _result(question, answer, intent, period, show_table, rows)


def _answer_holidays(question, normalized_question, plan, period, employee_id):
    wants_list = question_wants_list(normalized_question)
    is_upcoming = bool(UPCOMING_RE.search(normalized_question.lower()))
    result = _execute(
        {"operation_id": "holiday.list", "filters": dict(plan.get("filters", {}))},
        employee_id,
        limit=100,
    )
    rows = normalize_result_fields("holiday.list", result["data"])
    start, end = as_date(period.get("start_date")), as_date(period.get("end_date"))
    answer = holiday_answer(rows, start, end, wants_list, is_upcoming=is_upcoming)
    show_table = wants_list and bool(rows)
    return _result(question, answer, "holiday_lookup", period, show_table, rows)


def _combine_results(question: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    answer = "\n\n".join(result["answer"] for result in results)
    tables = [result for result in results if result.get("show_table")]
    show_table = len(tables) == 1
    return {
        "success": True,
        "question": question,
        "answer": answer,
        "message": answer,
        "intent": results[0]["intent"],
        "confidence": None,
        "period": results[0].get("period", {"start_date": None, "end_date": None}),
        "show_table": show_table,
        "raw_data": None,
        "data": tables[0]["data"] if show_table else [],
    }

YES_NO_START_RE = re.compile(r"^\s*(?:is|was|were|are|am|did|do|does|has|have|had)\b")
STATUS_TARGET_RE = re.compile(r"\b(approved|rejected|pending|submitted|draft|cancell?ed)\b")

def yes_no_status(question: str) -> str | None:
    """'approved', 'rejected', ... when the question is a yes/no check on a status, else None."""
    q = question.lower()
    if not YES_NO_START_RE.search(q):
        return None
    match = STATUS_TARGET_RE.search(q)
    if not match:
        return None
    return match.group(1).replace("canceled", "cancelled")

def request_entity(question: str) -> str | None:
    q = question.lower()
    if _WFH_RE.search(q):
        return "wfh_request"
    if _LEAVE_RE.search(q):
        return "leave_request"
    if TIMESHEET_RE.search(q):
        return "timesheet"
    return None

def _answer_status_check(question, normalized_question, plan, period, employee_id, target):
    operation_id = plan["operation_id"]
    kind = "leave" if operation_id.startswith("leave_") else "wfh"
    intent = "leave_status" if kind == "leave" else "wfh_status"
    filters = {key: value for key, value in plan.get("filters", {}).items() if key != "status"}
    result = _execute({"operation_id": operation_id, "filters": filters}, employee_id, limit=100)
    rows = normalize_result_fields(operation_id, result["data"])
    span = period_phrase(as_date(period.get("start_date")), as_date(period.get("end_date")))
    answer = status_check_answer(kind, rows, target, span)
    return _result(question, answer, intent, period, False, [])

def is_third_party_request(question: str) -> bool:
    """True when the question asks about someone other than the logged-in employee."""
    q = question.lower()
    for match in _POSSESSIVE_RE.finditer(q):
        if match.group(1) not in _SELF_POSSESSIVE_EXCLUSIONS:
            return True
    return bool(_THIRD_PARTY_WORDS_RE.search(q))

def _timesheet_overlaps(row: dict[str, Any], start: date, end: date) -> bool:
    period_start = as_date(row.get("period_start"))
    period_end = as_date(row.get("period_end")) or period_start
    if period_start is None:
        return False
    return period_start <= end and period_end >= start


def _answer_timesheet(question, normalized_question, period, employee_id, target):
    q = normalized_question.lower()
    start = as_date(period.get("start_date"))
    end = as_date(period.get("end_date"))
    submitted_basis = bool(SUBMITTED_DATE_RE.search(q)) and start is not None
    latest = bool(re.search(r"\b(?:latest|most\s+recent|recent|current)\b|\blast\s+timesheet\b", q))

    if submitted_basis:
        rows = _execute(
            {"operation_id": "timesheet.list",
             "filters": {"submitted_at": {"gte": start.isoformat(), "lte": end.isoformat()}}},
            employee_id, limit=100,
        )["data"]
    elif start is not None:
        # Timesheet periods are at most seven days, so a period that overlaps the day
        # must start within the six days before it. Overlap is checked in code.
        window_start = start - timedelta(days=6)
        rows = _execute(
            {"operation_id": "timesheet.list",
             "filters": {"period_start": {"gte": window_start.isoformat(), "lte": end.isoformat()}}},
            employee_id, limit=100,
        )["data"]
        rows = [row for row in rows if _timesheet_overlaps(row, start, end)]
    else:
        rows = _execute({"operation_id": "timesheet.list", "filters": {}}, employee_id, limit=100)["data"]

    rows = sorted(rows, key=lambda row: as_date(row.get("period_start")) or date.min, reverse=True)
    when = period_phrase(start, end) if start is not None else ""

    if not rows:
        if target:
            return _result(question, f"No, I couldn't find any timesheets {when}".rstrip() + ".",
                           "timesheet_lookup", period, False, [])
        return _result(question, f"I couldn't find any timesheets {when}".rstrip() + ".",
                       "timesheet_lookup", period, False, [])

    head = rows[0]
    period_start = as_date(head.get("period_start"))
    period_end = as_date(head.get("period_end")) or period_start
    period_text = f"for {fmt_range(period_start, period_end)}" if period_start else "on record"
    status = str(head.get("status") or "unknown").lower().replace("_", " ")
    submitted = as_date(head.get("submitted_at"))
    subject = "your most recent timesheet" if len(rows) > 1 else "your timesheet"

    if target:
        if status == target:
            verb = TIMESHEET_VERB.get(target, "is")
            answer = f"Yes, {subject} {period_text} {verb} {target}."
        else:
            answer = f"No, {subject} {period_text} is {status}."
    else:
        answer = f"{subject[0].upper() + subject[1:]} {period_text} has a status of {status}."
        if submitted_basis and submitted:
            answer += f" It was submitted on {submitted.day} {submitted:%B %Y}."

    return _result(question, answer, "timesheet_lookup", period, False, [])


def run_llm_chat(question: str, employee_id: int) -> dict[str, Any]:
    """Plan, correct with code, execute with the employee's scope, and answer in sentences."""
    parts = split_compound_question(question)
    if len(parts) > 1:
        return _combine_results(question, [run_llm_chat(part, employee_id) for part in parts])

    if is_third_party_request(question):
        return _text_result(question, THIRD_PARTY_MESSAGE, intent="unsupported")

    normalized_question = correct_typos(question)
    today = get_current_date()

    model_error: ModelServiceError | None = None
    try:
        raw_plan = get_query_plan(normalized_question)
    except ModelServiceError as exc:
        logger.warning("Model plan unavailable, using keyword plan: %s", exc)
        model_error = exc
        raw_plan = rule_based_plan(normalized_question)

    status_target = yes_no_status(normalized_question)
    entity = request_entity(normalized_question) if status_target else None
    if entity:
        raw_plan = {"operation_id": f"{entity}.list", "filters": {}}
    logger.info("question=%r plan=%r", normalized_question, raw_plan)

    if raw_plan.get("operation_id") not in set(OPERATION_DATE_FIELDS) | {"attendance.group_by"}:
        if isinstance(model_error, ModelUnavailableError):
            raise model_error
        return _text_result(question, UNSUPPORTED_MESSAGE, intent="unsupported")

    try:
        plan, period = normalize_and_correct_plan(raw_plan, normalized_question, today)
    except InvalidDateError as exc:
        answer = f"'{exc}' is not a valid date. Please check the day and month, for example: 19 October 2026."
        return _text_result(question, answer, intent="attendance_records")

    operation_id = plan["operation_id"]

    if operation_id == "attendance.list":
        return _answer_attendance(question, normalized_question, plan, period, employee_id)
    
    if operation_id in {"leave_request.list", "wfh_request.list"}:
        if status_target:
            return _answer_status_check(question, normalized_question, plan, period, employee_id, status_target)
        return _answer_requests(question, normalized_question, plan, period, employee_id)
    if operation_id == "holiday.list":
        return _answer_holidays(question, normalized_question, plan, period, employee_id)
    if operation_id == "timesheet.list" and (
        status_target or TIMESHEET_STATUS_Q_RE.search(normalized_question.lower())
    ):
        return _answer_timesheet(question, normalized_question, period, employee_id, status_target)

    asks_latest_timesheet = bool(
        operation_id == "timesheet.list"
        and re.search(
            r"\b(?:latest|most\s+recent|last|current)\s+timesheet\b",
            normalized_question.lower(),
        )
    )
    asks_pending_timesheets = bool(
        operation_id == "timesheet.list"
        and re.search(r"\bpending\b", normalized_question.lower())
    )

    execution_plan = dict(plan)
    if asks_pending_timesheets:
        execution_plan["filters"] = {
            key: value
            for key, value in plan.get("filters", {}).items()
            if key != "status"
        }

    query_result = _execute(
        execution_plan,
        employee_id,
        limit=1 if asks_latest_timesheet else 100 if asks_pending_timesheets else 50,
    )
    if asks_pending_timesheets:
        query_result["data"] = [
            row for row in query_result.get("data", [])
            if str(row.get("status") or "").strip().lower() in {"draft", "submitted"}
        ]

    operation = query_result["operation"]
    entity = query_result["entity"]
    data = normalize_result_fields(operation_id, query_result["data"])

    operation_to_intent = {
        "attendance.count": "attendance_summary",
        "attendance.sum": "attendance_summary",
        "attendance.group_by": "attendance_summary",
        "timesheet.list": "timesheet_lookup",
        "timesheet.count": "timesheet_lookup",
        "holiday.count": "holiday_lookup",
        "leave_request.count": "leave_status",
        "wfh_request.count": "wfh_status",
    }
    intent = operation_to_intent.get(operation_id, "attendance_records")

    if operation == "count":
        count = data.get("count", 0) if isinstance(data, dict) else 0
        nouns = {
            "attendance": ("attendance record", "attendance records"),
            "leave_request": ("leave request", "leave requests"),
            "wfh_request": ("work-from-home request", "work-from-home requests"),
            "timesheet": ("timesheet record", "timesheet records"),
            "holiday": ("holiday", "holidays"),
        }
        singular, plural = nouns.get(entity, ("record", "records"))
        noun = singular if count == 1 else plural
        status_filter = plan.get("filters", {}).get("status")
        status_text = f"{str(status_filter).replace('_', ' ').lower()} " if status_filter else ""
        span = period_phrase(as_date(period.get("start_date")), as_date(period.get("end_date")))
        answer = f"You had {count} {status_text}{noun}" + (f" {span}." if span else ".")
        return _result(question, answer, intent, period, False, data)

    if operation_id == "attendance.group_by":
        rows = data if isinstance(data, list) else []
        span = period_phrase(as_date(period.get("start_date")), as_date(period.get("end_date")))
        if ATTENDED_RE.search(normalized_question.lower()):
            breakdown = []
            attended_total = 0
            for row in rows:
                if not isinstance(row, dict):
                    continue
                key = str(row.get("group_value", "")).upper()
                count = row.get("record_count", 0)
                if key in ATTENDED_STATUSES and isinstance(count, int):
                    attended_total += count
                    breakdown.append(f"{count} {ATTENDED_STATUSES[key]}")
            noun = "day" if attended_total == 1 else "days"
            detail = f" ({', '.join(breakdown)})" if breakdown else ""
            answer = f"You attended {attended_total} {noun}" + (f" {span}" if span else "") + f"{detail}."
            return _result(question, answer, intent, period, False, data)
        if not rows:
            answer = "No matching attendance records were found."
        else:
            parts_text = []
            total = 0
            for row in rows:
                if not isinstance(row, dict):
                    continue
                group_value = str(row.get("group_value", "unknown")).replace("_", " ").lower()
                record_count = row.get("record_count", 0)
                if isinstance(record_count, (int, float)) and not isinstance(record_count, bool):
                    total += int(record_count)
                    parts_text.append(f"{int(record_count)} {group_value}")
            answer = f"You had {total} attendance records" + (f" {span}" if span else "") + f": {', '.join(parts_text)}."
        return _result(question, answer, intent, period, False, data)

    if operation == "sum":
        field = data.get("field", "value") if isinstance(data, dict) else "value"
        total = data.get("total") if isinstance(data, dict) else None
        span = period_phrase(as_date(period.get("start_date")), as_date(period.get("end_date")))
        date_ctx = f" {span}" if span else ""
        if field in {"worked_minutes", "overtime_minutes"} and isinstance(total, (int, float)) and not isinstance(total, bool):
            hours, minutes = divmod(int(total), 60)
            field_name = "worked time" if field == "worked_minutes" else "overtime"
            answer = f"Your total {field_name}{date_ctx} was {hours} hours and {minutes} minutes ({int(total):,} minutes)."
        else:
            answer = f"Your total for {field}{date_ctx} was {total}."
        return _result(question, answer, intent, period, False, data)

    if operation_id == "timesheet.list":
        timesheet_rows = query_result["data"] if isinstance(query_result["data"], list) else []
        if asks_latest_timesheet:
            if not timesheet_rows:
                message = "You don't have any timesheet records."
            else:
                row = timesheet_rows[0]
                start_date = row.get("period_start", row.get("work_date"))
                end_date = row.get("period_end")
                status = str(
                    row.get("status") or row.get("submission_status") or "unknown"
                ).replace("_", " ").title()
                if start_date and end_date:
                    period_text = (
                        f"for {start_date:%d %B %Y} to {end_date:%d %B %Y}"
                    )
                elif start_date:
                    period_text = f"for {start_date:%d %B %Y}"
                else:
                    period_text = "for the period on record"
                message = f"Your latest timesheet {period_text} has a status of {status}."
        elif asks_pending_timesheets and not timesheet_rows:
            message = "You don't have any pending timesheets."
        else:
            message = format_timesheet_response(timesheet_rows)
    elif isinstance(data, list):
        message = f"Found {len(data)} matching record(s)." if data else "No matching records were found."
    else:
        message = "Your requested information was retrieved."
    return _result(question, message, intent, period, isinstance(data, list) and bool(data), data)