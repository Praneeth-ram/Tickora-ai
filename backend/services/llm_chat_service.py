import logging
import os
import re
from collections import Counter
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


from backend.security.access_policy import AccessDenied, get_subject
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
from backend.services.operation_registry import build_operation_registry
from backend.services.leave_balance_answer import (
    answer_leave_balance,
    detect_metric,
    detect_year,
    enrich_rows,
    is_leave_balance_question,
    match_leave_type,
)
from backend.security.access_policy import ADMIN, SUPER_ADMIN, REFUSAL_MESSAGE, get_actor
from backend.services.dynamic_query_service import (
    TEAM_SUMMARY_LIMIT,
    execute_team_summary,
)

logger = logging.getLogger(__name__)


DEFAULT_TIMEZONE = os.getenv("APP_TIMEZONE", os.getenv("TICKORA_TIMEZONE", "Asia/Kolkata"))

UNSUPPORTED_MESSAGE = (
    "I can answer questions about your attendance, leave, work-from-home requests, "
    "holidays, and timesheets. Please ask about one of these."
)

OPERATION_DATE_FIELDS = {
    "payroll_summary.list": "period_start",
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
    "task.list": "task_date",
    "task.count": "task_date",
    "task.sum": "task_date",
    "task.group_by": "task_date",
}
DEFAULT_MONTH_OPERATIONS = {"attendance.list", "attendance.group_by", "attendance.sum"}
ALL_DATE_FILTER_KEYS = {
    "attendance_date", "start_date", "end_date", "period_start", "period_end",
    "holiday_date", "work_date", "applied_at", "requested_at", "submitted_at", "approved_at",
}
APPLIED_RE = re.compile(r"\b(?:appl(?:y|ied|ying|ication)|requested|submitted)\b")
UPCOMING_RE = re.compile(r"\b(?:upcoming|coming\s+up|next|remaining|future)\b")
ATTENDANCE_FIELDS = [
    "attendance_date", "clock_in", "clock_out", "status", "work_location",
    "worked_minutes", "overtime_minutes",
]
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
TIMESHEET_STATUS_PHRASES = {
    "approved": "has been approved",
    "rejected": "was rejected",
    "submitted": "has been submitted",
    "draft": "is a draft",
    "pending": "is pending",
}
TIMESHEET_STATUS_LABELS = {
    "draft": "a draft",
    "pending": "pending",
    "submitted": "submitted",
    "approved": "approved",
    "rejected": "rejected",
}
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
    except ZoneInfoNotFoundError:
        return date.today()


def get_query_plan(question: str) -> dict[str, Any]:
    """Generate a validated query plan with the in-process model."""
    # Imported here: model_inference imports this module for its error classes.
    from backend.services.model_inference import generate_plan

    return generate_plan(question)


_HOLIDAY_RE = re.compile(r"\bholidays?\b")
_PAYROLL_RE = re.compile(
    r"\b(?:payroll|salary|salaries|gross\s+pay|net\s+pay|"
    r"deductions?|deductible|deducted|take[- ]home\s+pay|"
    r"pay\s*slips?|payslips?|"
    r"credited\s+to\s+(?:my\s+)?account|"
    r"amount\s+(?:received|credited)|"
    r"(?:salary|pay)\s+(?:credited|deposited))\b",
    re.IGNORECASE,
)

def _is_payroll_query(question: str) -> bool:
    q = question.lower()

    is_loan_query = bool(
        re.search(
            r"\bloans?\b|\bpenalty\s+deduction\b",
            q,
        )
    )

    return bool(_PAYROLL_RE.search(q) and not is_loan_query)

_WFH_RE = re.compile(r"\bwfh\b|\bwork\s+from\s+home\b")
_LEAVE_RE = re.compile(r"\bleaves?\b")
_LEAVE_TYPE_LOOKUP_RE = re.compile(
    r"\b(?:leave\s+types?|types?\s+of\s+leave)\b",
    re.IGNORECASE,
)
_LEAVE_TYPE_AVAILABILITY_RE = re.compile(
    r"\b(?:available|offered|provided|can\s+i\s+use|"
    r"do\s+i\s+have\s+access|list|show|display)\b",
    re.IGNORECASE,
)
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
    elif is_leave_balance_question(q):
        entity = "leave_balance"
    elif re.search(r"\bleave\s+types?\b", q):
        entity = "leave_type"
    elif re.search(r"\btasks?\b", q):
        entity = "task"
    elif _LEAVE_RE.search(q):
        entity = "leave_request"
    elif re.search(r"\b(?:loans?|penalty\s+deduction)\b", q):
        entity = "loan_request"
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
    if re.search(r"\b(?:loans?|penalty\s+deduction)\b", q):
        return "loan"
    return None

DATE_PHRASE_RE = re.compile(
    r"(?:january|february|march|april|may|june|july|august|september|october|november|december)"
    r"\s+\d{1,2}(?:st|nd|rd|th)?\b",
    re.IGNORECASE,
)

def _date_phrase(part: str) -> str | None:
    match = DATE_PHRASE_RE.search(part)
    return match.group(0) if match else None

def _inherit_dates(parts: list[str]) -> list[str]:
    topics = [_primary_topic(part) for part in parts]
    topic_date: dict[str, str] = {}
    for part, topic in zip(parts, topics):
        phrase = _date_phrase(part)
        if phrase and topic and topic not in topic_date:
            topic_date[topic] = phrase
    result = []
    for part, topic in zip(parts, topics):
        if _date_phrase(part) is None and topic in topic_date:
            part = f"{part} on {topic_date[topic]}"
        result.append(part)
    return result


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
            return _inherit_dates(parts)
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
    "leave_balance": {"year", "leave_type_id"},
    "payroll_summary": {"period_start", "period_end"},
    "task": {
        "status", "project_id", "assigned_to_employee_id",
        "managed_by_employee_id",
    },
    "loan_request": {
        "status", "loan_status", "component",
        "mode", "start_month", "employee_id",
        "managed_by_employee_id",
    },
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


def _loan_metric_field(
    question: str,
    aggregate_fields: list[str],
) -> str | None:
    """Resolve a requested loan amount field from the approved field names."""
    q = question.lower()
    matches: list[tuple[int, str]] = []
    for field in aggregate_fields:
        if not field.endswith("_amount"):
            continue
        words = field.removesuffix("_amount").replace("_", " ")
        variants = {words}
        if words.endswith("ted"):
            variants.add(f"{words[:-3]}tion")

        for variant in variants:
            phrase = re.compile(
                r"\b(?:"
                + re.escape(variant)
                + r"\s+(?:loan\s+)?amount|"
                + r"amount\s+(?:(?:has\s+been|was|is)\s+)?"
                + re.escape(variant)
                + r"|how\s+much\s+(?:(?:has\s+been|was|is)\s+)?"
                + re.escape(variant)
                + r")\b"
            )
            match = phrase.search(q)
            if match:
                matches.append((match.start(), field))
            elif variant == "installment" and re.search(
                r"\binstallments?\b", q
            ):
                match = re.search(r"\binstallments?\b", q)
                if match:
                    matches.append((match.start(), field))
    return min(matches)[1] if matches else None


def _loan_component_phrase(
    question: str,
    metric_field: str | None,
) -> str | None:
    """Extract the component name without including the requested metric."""
    q = " ".join(question.strip().rstrip("?.!").split())

    match = re.search(
        r"\b(?:component(?:\s+is)?|for|on|of|from)\s+"
        r"(?:(?:my|the)\s+)?(?P<component>[^,;?.!]+)$",
        q,
        re.IGNORECASE,
    )

    if match is None:
        match = re.search(
            r"\b(?:my|the)\s+(?P<component>[\w &'/-]*?\s+loan)"
            r"(?:\s+requests?)?\s*$",
            q,
            re.IGNORECASE,
        )

    if match is None:
        return None

    component = match.group("component").strip(" '\"")
    component = re.sub(
        r"\s+loan\s+requests?$",
        " loan",
        component,
        flags=re.IGNORECASE,
    )
    component = re.sub(
        r"^(?:pending|approved|rejected|cancelled)\s+",
        "",
        component,
        flags=re.IGNORECASE,
    )

    # Remove the requested metric if it was included in the extracted phrase.
    if metric_field:
        metric_label = metric_field.replace("_", " ")
        component = re.sub(
            r"\s+" + re.escape(metric_label) + r"$",
            "",
            component,
            flags=re.IGNORECASE,
        ).strip()

    component = re.sub(
        r"^(?:(?:my|the)\s+)?loan\s+",
        "",
        component,
        flags=re.IGNORECASE,
    ).strip()

    if component.casefold() in {
        "loan", "loans", "loan request", "loan requests",
    }:
        return None

    return component or None


def _registered_entity_mentioned(
    question: str,
    registry: dict[str, dict[str, Any]],
) -> str | None:
    """Resolve an explicitly named entity using registered entity/table names."""
    matches: list[tuple[int, str]] = []
    seen: set[tuple[str, str]] = set()

    for definition in registry.values():
        entity = definition.get("entity")
        table = definition.get("table")
        if not isinstance(entity, str):
            continue

        for name in (entity, table):
            if not isinstance(name, str):
                continue
            phrase = name.replace("_", " ").strip()
            candidate = (entity, phrase)
            if not phrase or candidate in seen:
                continue
            seen.add(candidate)
            pattern = r"(?<!\w)" + re.escape(phrase).replace(
                r"\ ", r"\s+"
            ) + r"(?!\w)"
            if re.search(pattern, question, re.IGNORECASE):
                matches.append((len(phrase), entity))

    if not matches:
        return None

    matches.sort(reverse=True)
    return matches[0][1]


def _task_identity_filter(question: str) -> str | None:
    """Return the task ownership field explicitly requested by the user."""
    q = question.lower()
    if re.search(r"\bassigned(?:\s+to)?\s+me\b", q):
        return "assigned_to_employee_id"
    if re.search(
        r"\b(?:managed|manage|managing)\s+by\s+me\b"
        r"|\b(?:what|which)\s+tasks?\s+(?:am\s+i\s+)?managing\b"
        r"|\btasks?\s+(?:(?:which|that)\s+)?"
        r"(?:i\s+am|i['’]m)\s+managing\b"
        r"|\btasks?\s+(?:(?:which|that)\s+)?i\s+manage\b",
        q,
    ):
        return "managed_by_employee_id"
    return None

LOAN_VALUE_FIELDS = ("status", "loan_status", "mode")


def _loan_value_catalog(employee_id: int, organization_id: int | None) -> dict[str, list[str]]:
    """Distinct stored values for the requester's own loans (scope applied by the executor)."""
    result = _execute(
        {"operation_id": "loan_request.list", "fields": list(LOAN_VALUE_FIELDS), "filters": {}},
        employee_id,
        limit=100,
        organization_id=organization_id,
    )
    rows = [row for row in result.get("data") or [] if isinstance(row, dict)]
    return {
        field: sorted({str(row[field]) for row in rows if row.get(field)})
        for field in LOAN_VALUE_FIELDS
    }


def _loan_value_filters(question: str, catalog: dict[str, list[str]]) -> dict[str, str]:
    """Match stored values in the question. A value found in more than one field is ambiguous and is not applied."""
    q = question.lower()
    hits: dict[str, list[tuple[str, str]]] = {}
    for field, values in catalog.items():
        for value in values:
            pattern = r"(?<!\w)" + re.escape(value.replace("_", " ").lower()) + r"(?!\w)"
            if re.search(pattern, q):
                hits.setdefault(value.lower(), []).append((field, value))
    applied: dict[str, str] = {}
    for matched in hits.values():
        if len(matched) == 1:
            field, value = matched[0]
            applied[field] = value
    return applied


def _describe_loan_matches(rows: list[dict[str, Any]], applied: dict[str, str]) -> str:
    """One sentence naming the filter applied and the matching loans."""
    condition = " and ".join(
        f"{field.replace('_', ' ')} {value}" for field, value in applied.items()
    )
    if not rows:
        return f"You have no loans with {condition}."
    shown = []
    for row in rows[:10]:
        others = [
            f"{field.replace('_', ' ')} {row.get(field)}"
            for field in ("status", "loan_status")
            if field not in applied and row.get(field)
        ]
        detail = f" ({', '.join(others)})" if others else ""
        shown.append(f"{row.get('component')}{detail}")
    noun = "loan" if len(rows) == 1 else "loans"
    more = f" Showing 10 of {len(rows)}." if len(rows) > 10 else ""
    return f"You have {len(rows)} {noun} with {condition}: {'; '.join(shown)}.{more}"


def normalize_and_correct_plan(
    plan: dict[str, Any],
    question: str,
    today: date,
    loan_values: dict[str, list[str]] | None = None,
) -> tuple[dict[str, Any], dict[str, str | None]]:
    """Correct the model's plan with code: operation, status, and every date."""
    normalized = dict(plan)
    q = question.lower()
    op_id = normalized.get("operation_id", "")
    asks_work_location = bool(WORK_LOCATION_RE.search(q))

    normalized.pop("group_by_field", None)
    normalized.pop("aggregate_function", None)

    if asks_work_location:
        op_id = "attendance.list"
        normalized["operation_id"] = op_id
        for key in ("group_by_field", "aggregate_function", "aggregate_field"):
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
    r"\b(?:leave|wfh|work from home|timesheet|holiday|loan|task)\b",
    q,
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
        # Guard: leave-balance questions use "how many" too — do NOT reroute them
        # to leave_request.count.  is_leave_balance_question already short-circuits
        # in run_llm_chat, but this protects against model plans that reach here.
        if re.search(r"\bleave\s+types?\b", q):
            op_id = "leave_type.count"
        elif "leave" in q and not is_leave_balance_question(q):
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
    
        # Correct task routing independently of the model's initial choice.
    valid_statuses_by_entity = {
        "attendance": {"present", "late", "absent", "half_day", "on_leave", "work_from_home"},
        "leave_request": {"pending", "approved", "rejected", "cancelled"},
        "wfh_request": {"pending", "approved", "rejected", "cancelled"},
        "timesheet": {"draft", "submitted", "approved", "rejected"},
        "task": {"pending", "completed", "in_progress", "cancelled"},
        "loan_request": {
            "active", "pending", "approved", "rejected", "cancelled",
        },
    }
    status_keywords = {
        "late": "late", "absent": "absent", "present": "present",
        "half day": "half_day", "half-day": "half_day", "pending": "pending",
        "approved": "approved", "rejected": "rejected", "cancelled": "cancelled",
        "active": "active",
        "draft": "draft", "submitted": "submitted",
        "in progress": "in_progress","completed": "completed"
    }

    is_task_query = bool(re.search(r"\btasks?\b", q))
    task_statuses = {
        status_value
        for word, status_value in status_keywords.items()
        if status_value in valid_statuses_by_entity["task"]
        and re.search(r"\b" + re.escape(word) + r"\b", q)
    }
    is_multi_status_task_count = (
        is_task_query and is_count_query and len(task_statuses) > 1
    )
    registry = build_operation_registry()

    # Prefer an entity explicitly named by the user over a conflicting model
    # classification. Entity and table names come from the approved registry.
    requested_entity = _registered_entity_mentioned(question, registry)
    if requested_entity:
        grouped_request = bool(
            re.search(
                r"\b(?:group(?:ed)?|breakdown|break\s+down|"
                r"categorize|category)\b",
                q,
            )
            and re.search(r"\bby\b", q)
        )
        if grouped_request:
            group_definition = registry.get(
                f"{requested_entity}.group_by"
            )
            group_fields = (
                group_definition.get("group_by_fields", [])
                if group_definition
                else []
            )
            group_by_field = next(
                (
                    field
                    for field in sorted(
                        group_fields,
                        key=len,
                        reverse=True,
                    )
                    if re.search(
                        r"\bby\s+"
                        + re.escape(field.replace("_", " "))
                        .replace(r"\ ", r"\s+")
                        + r"(?!\w)",
                        q,
                    )
                ),
                None,
            )
            if group_definition and group_by_field:
                op_id = f"{requested_entity}.group_by"
                normalized.update(
                    {
                        "operation_id": op_id,
                        "group_by_field": group_by_field,
                        "aggregate_function": "count",
                    }
                )
                for key in ("fields", "aggregate_field"):
                    normalized.pop(key, None)
            else:
                requested_entity = None

        if requested_entity and not grouped_request:
            requested_operation = (
                "count" if is_count_query else "list"
            )
            operation_id = (
                f"{requested_entity}.{requested_operation}"
            )
            if operation_id in registry:
                op_id = operation_id
                normalized["operation_id"] = operation_id

    task_sum_definition = registry.get("task.sum", {})
    task_aggregate_fields = task_sum_definition.get("aggregate_fields", [])
    task_aggregate_field = next(
        (
            field
            for field in task_aggregate_fields
            if re.search(
                r"\b" + re.escape(field.replace("_", " ")).replace(r"\ ", r"\s+") + r"s?\b",
                q,
            )
        ),
        None,
    )
    has_task_sum_intent = bool(re.search(r"\b(?:sum|aggregate)\b", q))
    if (
        is_task_query
        and has_task_sum_intent
        and task_aggregate_field is None
        and len(task_aggregate_fields) == 1
    ):
        task_aggregate_field = task_aggregate_fields[0]
    asks_task_sum = bool(
        task_aggregate_field
        and (
            has_task_sum_intent
            or re.search(r"\b(?:total|combined|overall)\b", q)
        )
    )

    if is_task_query:
        if is_multi_status_task_count:
            op_id = "task.group_by"
            normalized.update({
                "operation_id": op_id,
                "group_by_field": "status",
                "aggregate_function": "count",
            })
            for key in ("fields", "aggregate_field"):
                normalized.pop(key, None)
        elif is_count_query:
            op_id = "task.count"
        elif asks_task_sum or op_id == "task.sum":
            op_id = "task.sum"
        else:
            op_id = "task.list"

        normalized["operation_id"] = op_id

        if op_id == "task.sum":
            if task_aggregate_field:
                normalized["aggregate_field"] = task_aggregate_field
            for key in ("fields", "group_by_field", "aggregate_function"):
                normalized.pop(key, None)
        elif op_id == "task.count":
            for key in (
                "fields",
                "group_by_field",
                "aggregate_function",
                "aggregate_field",
            ):
                normalized.pop(key, None)

            # Correct Loan Request routing independently of the model's initial choice.
    is_loan_request_query = bool(
        re.search(r"\b(?:loan|loans)\b|\bpenalty\s+deduction\b", q)
    )

    if is_loan_request_query:
        loan_definition = registry.get("loan_request.list", {})
        loan_aggregate_fields = registry.get(
            "loan_request.sum", {}
        ).get("aggregate_fields", [])
        loan_metric_field = _loan_metric_field(
            question,
            list(loan_definition.get("fields", []))
            + loan_aggregate_fields,
        )
        is_loan_count_query = bool(
            re.search(r"\b(?:how\s+many|count|number\s+of)\b", q)
        )

        is_loan_aggregate_query = bool(
            re.search(r"\b(?:sum|total|aggregate)\b", q)
        )

        if is_loan_aggregate_query:
            op_id = "loan_request.sum"
        elif is_loan_count_query:
            op_id = "loan_request.count"
        else:
            op_id = "loan_request.list"

        normalized["operation_id"] = op_id

        for key in (
            "group_by_field",
            "aggregate_function",
            "fields",
        ):
            normalized.pop(key, None)

        if op_id == "loan_request.sum":
            if loan_metric_field:
                normalized["aggregate_field"] = loan_metric_field
        else:
            normalized.pop("aggregate_field", None)
            if (
                op_id == "loan_request.list"
                and loan_metric_field
                and loan_metric_field in loan_definition.get("fields", [])
            ):
                normalized["fields"] = ["component", loan_metric_field]
            
    op_id = normalized.get("operation_id", op_id)
    entity = op_id.split(".")[0] if op_id else ""
    allowed_filters = ALLOWED_FILTERS.get(entity, set())
    allowed_filters = ALLOWED_FILTERS.get(entity, set())
    # Read identity-reference rules from the approved operation registry.
    # Read identity-reference rules from the approved operation registry.
    definition = registry.get(op_id, {})
    identity_filters = definition.get("identity_filters", {})

    filters = {}
    for key, value in (normalized.get("filters") or {}).items():
        if key not in allowed_filters or key in ALL_DATE_FILTER_KEYS:
            continue

        # Convert self-references only for fields explicitly approved by metadata.
        if key in identity_filters and isinstance(value, str):
            if value.strip().lower() in {
                "me", "myself", "my", "current user", "employee_id",
            }:
                filters[key] = {"$context": identity_filters[key]}
                continue

    # Preserve only a valid, registry-approved structured identity reference.
        if isinstance(value, dict):
            if (
                key in identity_filters
                and value == {"$context": identity_filters[key]}
            ):
                filters[key] = value   
                continue

        filters[key] = value
    
    # Prevent a loan component name from being interpreted as loan_status.
    if op_id.startswith("loan_request.") and loan_values is not None:
        for key in LOAN_VALUE_FIELDS:
            filters.pop(key, None)
        filters.update(_loan_value_filters(question, loan_values))

    explicit_status = None
    for word, status_value in status_keywords.items():
        if word == "submitted" and SUBMITTED_DATE_RE.search(q):
            continue
        status_pattern = re.escape(word).replace(
            r"\ ", r"[\s-]+"
        )
        if re.search(r"\b" + status_pattern + r"\b", q):
            explicit_status = status_value
            break

    if explicit_status:
        if op_id in {
            "attendance.list", "attendance.count", "attendance.group_by",
            "leave_request.list", "leave_request.count",
            "wfh_request.list", "wfh_request.count",
            "timesheet.list", "timesheet.count",
            "task.list", "task.count", "task.sum", "task.group_by",
        } and not (
            op_id in {"attendance.group_by", "task.group_by"}
            and normalized.get("group_by_field") == "status"
        ):
            if op_id.startswith("loan_request."):
                filters.pop("status", None)
                filters["loan_status"] = explicit_status
            else:
                filters["status"] = explicit_status
    else:
        # The user named no status, so drop any status filter the model added.
        filters.pop("status", None)

    if op_id == "task.group_by" and normalized.get("group_by_field") == "status":
        filters.pop("status", None)

    entity_statuses = valid_statuses_by_entity.get(entity)
    if (
        entity_statuses
        and entity != "loan_request"
        and filters.get("status") not in entity_statuses
    ):
        filters.pop("status", None)

    if is_attended_query:
        filters.pop("status", None)

    # Resolve Loan Request identity from the authenticated employee.
    # Default loan queries refer to the employee's own requests.
    if op_id.startswith("loan_request."):
        manager_intent = bool(
            re.search(
                r"\b(?:managed|manage|managing)\s+by\s+me\b"
                r"|\b(?:what|which)\s+loan\s+requests?\s+"
                r"(?:am\s+i\s+)?managing\b"
                r"|\bhow\s+many\s+loan\s+requests?\s+"
                r"am\s+i\s+managing\b"
                r"|\bloan\s+requests?\s+i\s+manage\b",
                q,
            )
        )

        if manager_intent:
            context = identity_filters.get(
                "managed_by_employee_id"
            )
            if context:
                filters.pop("employee_id", None)
                filters["managed_by_employee_id"] = {
                    "$context": context
                }
        else:
            context = identity_filters.get("employee_id")
            if context:
                filters.pop("managed_by_employee_id", None)
                filters["employee_id"] = {
                    "$context": context
                }

    if op_id.startswith("task."):
        identity_field = _task_identity_filter(q)
        if identity_field:
            context = identity_filters.get(identity_field)
            if context:
                filters[identity_field] = {"$context": context}

    date_field = OPERATION_DATE_FIELDS.get(op_id)
    if date_field is None:
        date_field = registry.get(op_id, {}).get("date_field")
    if op_id.startswith("timesheet.") and SUBMITTED_DATE_RE.search(q):
        date_field = "submitted_at"
    if date_field and op_id.startswith(("leave_request.", "wfh_request.")) and APPLIED_RE.search(q):
        date_field = "applied_at"

    date_range = resolve_date_range_from_question(question, today)
    if date_range is not None:
        if UPCOMING_RE.search(q) and date_field and date_range[1] >= today:
            if date_range[0] < today:
                date_range = (today, date_range[1])
        if date_field:
            exclusive_bound = None
            if date_field == "task_date" and date_range[0] == date_range[1]:
                match = re.search(r"\b(after|before)\b", q)
                if match:
                    exclusive_bound = match.group(1)

            if exclusive_bound == "after":
                filters[date_field] = {
                    "gte": (date_range[1] + timedelta(days=1)).isoformat()
                }
                date_range = None
            elif exclusive_bound == "before":
                filters[date_field] = {
                    "lte": (date_range[0] - timedelta(days=1)).isoformat()
                }
                date_range = None
            else:
                filters[date_field] = {
                    "gte": date_range[0].isoformat(),
                    "lte": date_range[1].isoformat(),
                }
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
        return "No timesheets were found for the requested period."

    shown = data[:10]
    heading = "Your timesheet:" if len(data) == 1 else f"Your {len(data)} timesheets:"
    lines = [heading]
    for row in shown:
        start = as_date(row.get("period_start") or row.get("work_date"))
        end = as_date(row.get("period_end")) or start
        if start and end:
            period = fmt_range(start, end)
        elif start:
            period = f"{start.day} {start:%B %Y}"
        else:
            period = "Period not recorded"
        status_value = row.get("status") or row.get("submission_status")
        status = str(status_value).replace("_", " ").title() if status_value else None
        lines.append(f"- {period}" + (f": {status}" if status else ""))
    if len(data) > len(shown):
        lines.append(f"Showing {len(shown)} of {len(data)} timesheets.")
    return "\n".join(lines)



def count_response(
    entity: str,
    count: int,
    status: str | None,
    span: str,
    filters: dict[str, Any] | None = None,
    question: str = "",
) -> str:
    """Generate a meaningful count response from the query result and filters."""

    nouns = {
        "attendance": ("attendance record", "attendance records"),
        "leave_request": ("leave request", "leave requests"),
        "wfh_request": (
            "work-from-home request",
            "work-from-home requests",
        ),
        "timesheet": ("timesheet", "timesheets"),
        "holiday": ("holiday", "holidays"),
        "leave_balance": ("leave balance", "leave balances"),
        "leave_type": ("leave type", "leave types"),
        "loan_request": ("loan request", "loan requests"),
        "task": ("task", "tasks"),
    }

    singular, plural = nouns.get(entity, ("record", "records"))
    noun = singular if count == 1 else plural

    filters = filters or {}

    status_text = (
        status.replace("_", " ").strip().lower()
        if status
        else ""
    )

    loan_status = filters.get("loan_status")
    loan_status_text = (
        str(loan_status).replace("_", " ").strip().lower()
        if loan_status
        else ""
    )

    qualifiers = (
        [loan_status_text]
        if loan_status_text
        else ([status_text] if status_text else [])
    )
    description = " ".join(qualifiers + [noun])

    where = f" {span}" if span else ""

    # Detect manager-scoped Loan Request counts using query metadata.
    managed_by = filters.get("managed_by_employee_id")

    is_managed_by_self = (
        managed_by == {"$context": "employee_id"}
        or (
            isinstance(managed_by, int)
            and not isinstance(managed_by, bool)
        )
    )

    if entity == "loan_request" and is_managed_by_self:
        if count == 0:
            return f"You are not managing any {plural}{where}."

        return (
            f"You are managing {count} {description}{where}."
        )

    # Handle normal personal Loan Request counts.
    employee_filter = filters.get("employee_id")
    is_personal_loan_query = (
        entity == "loan_request"
        and employee_filter == {"$context": "employee_id"}
    )

    if is_personal_loan_query:
        if count == 0:
            return f"You have no {description}{where}."

        return f"You have {count} {description}{where}."

    # Generic entity count responses.
    if count == 0:
        return f"No {description} were found{where}."

    if entity in {"holiday", "leave_type"}:
        return (
            f"There {'is' if count == 1 else 'are'} "
            f"{count} {description}{where}."
        )

    return f"You have {count} {description}{where}."


def loan_amount_response(
    data: Any,
    metric_field: str,
    component: str | None,
    span: str = "",
) -> str:
    """Format database loan amount values for a requested metric."""
    metric_label = metric_field.replace("_", " ")
    where = f" {span}" if span else ""
    if isinstance(data, dict):
        if data.get("record_count", 0) == 0:
            return _no_loan_records_message(component)
        amount = data.get("total")
        if amount is None:
            return _no_loan_amount_message(component, metric_label)
        return (
            f"The {metric_label} for {component or 'your loans'} "
            f"is {_format_loan_amount(amount)}{where}."
        )

    rows = data if isinstance(data, list) else []
    if not rows:
        return _no_loan_records_message(component)

    answers = []
    for row in rows:
        row_component = str(row.get("component") or component or "your loan")
        amount = row.get(metric_field)
        if amount is None:
            answers.append(
                f"No {metric_label} is recorded for {row_component}."
            )
        else:
            answers.append(
                f"The {metric_label} for {row_component} is "
                f"{_format_loan_amount(amount)}{where}."
            )
    return " ".join(answers)


def _format_loan_amount(value: Any) -> str:
    if isinstance(value, bool):
        raise ModelServiceError("The loan query returned a non-numeric amount.")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ModelServiceError(
            "The loan query returned a non-numeric amount."
        ) from exc
    return format(amount, ",.2f")


def _no_loan_records_message(component: str | None) -> str:
    if component:
        return f"No loan records were found for {component}."
    return "No loan records were found."


def _no_loan_amount_message(
    component: str | None,
    metric_label: str,
) -> str:
    if component:
        return f"No {metric_label} is recorded for {component}."
    return f"No {metric_label} is recorded for your loans."


def task_count_response(
    count: int,
    filters: dict[str, Any],
    question: str,
    span: str,
    employee_id: int,
) -> str:
    """Describe a task count using the filters that scoped the query."""
    status = filters.get("status")
    status_text = (
        str(status).replace("_", " ").strip().lower()
        if isinstance(status, str) and status.strip()
        else ""
    )
    task_noun = "task" if count == 1 else "tasks"
    description = f"{status_text + ' ' if status_text else ''}{task_noun}"
    q = question.lower()

    assigned_to = filters.get("assigned_to_employee_id")
    managed_by = filters.get("managed_by_employee_id")
    assigned_to_self = (
        assigned_to == employee_id
        or assigned_to == {"$context": "employee_id"}
        or bool(re.search(r"\bassigned(?:\s+to)?\s+me\b", q))
    )
    managed_by_self = (
        managed_by == employee_id
        or managed_by == {"$context": "employee_id"}
        or bool(re.search(r"\b(?:managed|managing|manage)\s+by\s+me\b", q))
    )
    organization_query = bool(
        re.search(r"\b(?:organization|organisation|company|org)\b", q)
    )

    qualifiers: list[str] = []
    if assigned_to is not None or assigned_to_self:
        if assigned_to_self:
            qualifiers.append("assigned to you")
        elif isinstance(assigned_to, (int, str)) and str(assigned_to).isdigit():
            qualifiers.append(f"assigned to employee {assigned_to}")
    elif managed_by is not None or managed_by_self:
        if managed_by_self:
            qualifiers.append("managed by you")
        elif isinstance(managed_by, (int, str)) and str(managed_by).isdigit():
            qualifiers.append(f"managed by employee {managed_by}")

    project_id = filters.get("project_id")
    if isinstance(project_id, (int, str)) and str(project_id).isdigit():
        qualifiers.append(f"for project {project_id}")

    if organization_query:
        if assigned_to is None and managed_by is None:
            qualifiers.append(
                "in your organization that you're assigned to or manage"
            )
        else:
            qualifiers.append("in your organization")

    if span:
        qualifiers.append(span)

    where = f" {' '.join(qualifiers)}" if qualifiers else ""

    if count == 0:
        return f"No {description}{where} were found."

    if assigned_to_self and not organization_query:
        return f"You have {count} {description}{where}."
    if managed_by_self and not organization_query:
        managed_qualifiers = [
            qualifier for qualifier in qualifiers if qualifier != "managed by you"
        ]
        managed_where = (
            f" {' '.join(managed_qualifiers)}"
            if managed_qualifiers
            else ""
        )
        return f"You manage {count} {description}{managed_where}."

    verb = "is" if count == 1 else "are"
    return f"There {verb} {count} {description}{where}."


def sum_response(field: str, total: Any, span: str) -> str:
    if not isinstance(total, (int, float, Decimal)) or isinstance(total, bool):
        raise ModelServiceError("The query returned a non-numeric aggregate.")

    where = f" {span}" if span else ""
    value = Decimal(str(total))
    if field in {"worked_minutes", "overtime_minutes"}:
        minutes_total = int(value)
        hours, minutes = divmod(minutes_total, 60)
        if field == "overtime_minutes":
            return f"You recorded {hours} hours and {minutes} minutes of overtime{where}."
        return f"You worked {hours} hours and {minutes} minutes{where}."

    day_fields = {
        "allocated_days": "allocated leave",
        "used_days": "used leave",
        "pending_days": "pending leave",
    }
    if field in day_fields:
        day_count = "day" if value == 1 else "days"
        return f"Your total {day_fields[field]}{where} is {format(value, 'f')} {day_count}."

    if field == "performance_score":
        return (
            f"Your total task performance score{where} "
            f"is {format(value, 'f')}."
        )

    label = field.replace("_", " ").strip()
    return f"The total {label}{where} is {format(value, 'f')}."


def grouped_response(
    entity: str,
    rows: list[dict[str, Any]],
    group_by_field: str | None,
    aggregate_function: str | None,
    aggregate_field: str | None,
    span: str,
    group_labels: dict[Any, str] | None = None,
) -> str:
    entity_labels = {
        "attendance": ("attendance", "day"),
        "task": ("task", "task"),
        "leave_balance": ("leave balance", "record"),
    }
    title, count_unit = entity_labels.get(
        entity,
        (entity.replace("_", " "), "record"),
    )

    if not rows:
        where = f" {span}" if span else ""
        return f"No {title} breakdown is available{where}."

    field_labels = {
        "status": "status",
        "work_location": "work location",
        "is_late": "late status",
        "year": "year",
        "leave_type_id": "leave type",
    }
    dimension = field_labels.get(group_by_field or "", "category")
    where = f" {span}" if span else ""
    parts = []
    for row in rows:
        value = row.get("group_value")
        label = (group_labels or {}).get(value)
        if label is None and group_by_field == "status":
            label = str(value or "unknown").replace("_", " ").lower()
        elif label is None and group_by_field == "is_late":
            label = "late" if value is True else "not late" if value is False else "unknown"
        elif label is None:
            label = str(value if value is not None else "not recorded").replace("_", " ").title()

        if aggregate_function == "sum":
            amount = row.get("total", 0)
            if aggregate_field in {"worked_minutes", "overtime_minutes"}:
                minutes_total = int(amount or 0)
                hours, minutes = divmod(minutes_total, 60)
                measure = f"{hours} hours and {minutes} minutes"
            elif aggregate_field in {"allocated_days", "used_days", "pending_days"}:
                measure = f"{format(Decimal(str(amount or 0)), 'f')} days"
            else:
                measure = str(amount)
        else:
            count = row.get("record_count", 0)
            measure = f"{count} {count_unit}{'s' if count != 1 else ''}"
        parts.append(f"{label}: {measure}")
    return f"Your {title} breakdown by {dimension}{where}: {', '.join(parts)}."


def leave_type_response(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No leave types are currently available."
    names = []
    for row in rows[:10]:
        name = str(row.get("name") or row.get("code") or "Leave type").strip()
        paid = row.get("is_paid")
        names.append(f"{name} ({'paid' if paid else 'unpaid'})" if paid is not None else name)
    noun = "leave type" if len(rows) == 1 else "leave types"
    answer = f"There {'is' if len(rows) == 1 else 'are'} {len(rows)} {noun}: {', '.join(names)}."
    if len(rows) > 10:
        answer += f" Showing 10 of {len(rows)}."
    return answer


def _payroll_response(
    rows: Any,
    period: dict[str, Any],
    question: str = "",
) -> str:
    """Format payroll results as a specific amount, aggregate, extremum, or breakdown."""
    if not isinstance(rows, list) or not rows:
        start = as_date(period.get("start_date"))
        end = as_date(period.get("end_date"))
        span = period_phrase(start, end)
        return (
            f"No payroll records were found"
            f"{f' {span}' if span else ''}."
        )

    q = question.lower()

    if re.search(
    r"\b(?:deductions?|deductible|deductibles|"
    r"tax(?:es)?\s+deducted|"
    r"deduction\s+amount|deducted(?:\s+(?:amount|from|for))?)\b",
    q,
    ):
        metric = "deduction_amount"
        label = "deductions"

    elif re.search(
        r"\b(?:net\s+(?:amount|salary|pay|income)|"
        r"take[- ]home\s+(?:pay|salary|amount)|"
        r"amount\s+(?:received|credited)|"
        r"credited\s+to\s+(?:my\s+)?account)\b",
        q,
    ):
        metric = "net_amount"
        label = "net salary"

    elif re.search(
        r"\b(?:gross\s+(?:amount|salary|pay|earnings)|"
        r"earnings\s+before\s+deductions)\b",
        q,
    ):
        metric = "gross_amount"
        label = "gross salary"

    else:
        metric = None
        label = None

    def money(value: Any) -> str:
        if value is None:
            return "not recorded"
        return f"{Decimal(str(value)):,.2f}"

    def period_label(row: dict[str, Any]) -> str:
        start = as_date(row.get("period_start"))
        end = as_date(row.get("period_end"))

        if start and end:
            return fmt_range(start, end)
        if start:
            return f"{start.day} {start:%B %Y}"
        return "period not recorded"

    # Calculate totals only when the question explicitly requests an aggregate.
    asks_total = bool(
        re.search(
            r"\b(?:total|cumulative|combined|sum\s+of|overall\s+total)\b",
            q,
        )
    )

    # Detect highest/lowest-value questions.
    asks_highest = bool(
        re.search(
            r"\b(?:highest|maximum|max(?:imum)?|largest|greatest)\b",
            q,
        )
    )
    asks_lowest = bool(
        re.search(
            r"\b(?:lowest|minimum|min(?:imum)?|smallest|least)\b",
            q,
        )
    )

    if metric and (asks_highest or asks_lowest):
        valid_rows = []
        for row in rows:
            value = row.get(metric)
            if value is not None:
                try:
                    valid_rows.append((Decimal(str(value)), row))
                except (InvalidOperation, ValueError, TypeError):
                    continue

        if not valid_rows:
            return f"No recorded {label} amounts were found."

        selected_value, selected_row = (
            max(valid_rows, key=lambda item: item[0])
            if asks_highest
            else min(valid_rows, key=lambda item: item[0])
        )

        currency = str(selected_row.get("currency") or "").strip()
        prefix = f"{currency} " if currency else ""
        qualifier = "highest" if asks_highest else "lowest"

        return (
            f"Your {qualifier} recorded {label} was "
            f"{prefix}{money(selected_value)} for "
            f"{period_label(selected_row)}."
        )

   
    if metric and asks_total:
        start = as_date(period.get("start_date"))
        end = as_date(period.get("end_date"))

        # Validate monthly payroll coverage before reporting a range total.
        if start and end:
            requested_months = []
            cursor = start.replace(day=1)
            last_month = end.replace(day=1)

            while cursor <= last_month:
                requested_months.append((cursor.year, cursor.month))

                if cursor.month == 12:
                    cursor = date(cursor.year + 1, 1, 1)
                else:
                    cursor = date(cursor.year, cursor.month + 1, 1)

            recorded_months = set()

            for row in rows:
                row_start = as_date(row.get("period_start"))
                row_end = as_date(row.get("period_end"))

                if row_start and row_end:
                    # A payroll record covers every calendar month it overlaps.
                    month_cursor = row_start.replace(day=1)
                    month_end = row_end.replace(day=1)

                    while month_cursor <= month_end:
                        recorded_months.add(
                            (month_cursor.year, month_cursor.month)
                        )

                        if month_cursor.month == 12:
                            month_cursor = date(
                                month_cursor.year + 1, 1, 1
                            )
                        else:
                            month_cursor = date(
                                month_cursor.year,
                                month_cursor.month + 1,
                                1,
                            )

            missing_months = [
                date(year, month, 1).strftime("%B %Y")
                for year, month in requested_months
                if (year, month) not in recorded_months
            ]

            if missing_months:
                missing_text = ", ".join(missing_months)

                return (
                    f"Payroll data is missing for {missing_text}. "
                    f"I can't confirm the complete {label} for "
                    f"{period_phrase(start, end)} because the requested "
                    f"period has missing payroll data."
                )

        # Existing total calculation: preserve currency separation.
        totals: dict[str, Decimal] = {}

        for row in rows:
            value = row.get(metric)
            if value is None:
                continue

            currency = (
                str(row.get("currency") or "").strip()
                or "unspecified currency"
            )

            try:
                totals[currency] = (
                    totals.get(currency, Decimal("0"))
                    + Decimal(str(value))
                )
            except (InvalidOperation, ValueError, TypeError):
                continue

        if not totals:
            return f"No recorded {label} amounts were found to total."

        start = as_date(period.get("start_date"))
        end = as_date(period.get("end_date"))
        span = period_phrase(start, end)
        where = f" {span}" if span else ""

        if len(totals) == 1:
            currency, total = next(iter(totals.items()))
            prefix = (
                ""
                if currency == "unspecified currency"
                else f"{currency} "
            )
            return (
                f"Your total {label}{where} was "
                f"{prefix}{money(total)}."
            )

        amounts = "; ".join(
            f"{currency}: {money(total)}"
            for currency, total in sorted(totals.items())
        )
        return f"Your total {label}{where} was {amounts}."

    # For a specific metric without a total/highest/lowest request,
    # show only that metric for each matching payroll period.
    if metric:
        if metric == "net_amount":
            lines = []
            for row in rows[:20]:
                value = money(row.get(metric))
                currency = str(row.get("currency") or "").strip()
                prefix = f"{currency} " if currency else ""
                lines.append(
                    f"Your net pay for {period_label(row)} was "
                    f"{prefix}{value}."
                )
            return "\n".join(lines)

        lines = []
        for row in rows[:20]:
            value = money(row.get(metric))
            currency = str(row.get("currency") or "").strip()
            prefix = f"{currency} " if currency else ""
            lines.append(
                f"- {label.capitalize()} for {period_label(row)}: "
                f"{prefix}{value}."
            )

        heading = {
            "gross_amount": "Your gross salary:",
            "deduction_amount": "Your payroll deductions:",
        }[metric]

        return heading + "\n" + "\n".join(lines)

    # General salary/payroll questions retain the full breakdown.
    lines = []
    for row in rows[:20]:
        currency = str(row.get("currency") or "").strip()
        prefix = f"{currency} " if currency else ""

        lines.append(
            f"- {period_label(row)}: "
            f"Gross {prefix}{money(row.get('gross_amount'))}; "
            f"deductions {prefix}{money(row.get('deduction_amount'))}; "
            f"net {prefix}{money(row.get('net_amount'))}."
        )

    if len(rows) > 20:
        lines.append(f"Showing 20 of {len(rows)} payroll records.")

    return "Your payroll records:\n" + "\n".join(lines)

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


_CAPTURE_COMBINED_ANSWERS: ContextVar[bool] = ContextVar(
    "capture_combined_answers", default=False
)


@contextmanager
def _capture_combined_answers():
    token = _CAPTURE_COMBINED_ANSWERS.set(True)
    try:
        yield
    finally:
        _CAPTURE_COMBINED_ANSWERS.reset(token)


_TABLE_RECORD_NAMES = {
    "attendance_records": ("attendance record", "attendance records"),
    "holiday_lookup": ("holiday", "holidays"),
    "leave_balance": ("leave balance", "leave balances"),
    "leave_status": ("leave request", "leave requests"),
    "leave_type_lookup": ("leave type", "leave types"),
    "payroll_lookup": ("payroll record", "payroll records"),
    "team_attendance": ("team member", "team members"),
    "timesheet_lookup": ("timesheet", "timesheets"),
    "wfh_status": ("work-from-home request", "work-from-home requests"),
}


def _table_intro(
    intent: str,
    data: Any,
    period: dict[str, Any],
) -> str:
    count = len(data) if isinstance(data, list) else int(data is not None)
    singular, plural = _TABLE_RECORD_NAMES.get(intent, ("record", "records"))
    noun = singular if count == 1 else plural
    verb = "is" if count == 1 else "are"
    intro = f"Here {verb} your {count} {noun}"

    start = as_date(period.get("start_date"))
    end = as_date(period.get("end_date"))
    span = period_phrase(start, end)
    if span:
        span = re.sub(r"^(?:in|on|from)\s+", "", span)
        intro += f" for {span}"
    return intro + "."


def _result(
    question: str,
    answer: str,
    intent: str,
    period: dict[str, Any],
    show_table: bool,
    data: Any,
    raw_data: Any = None,
    loan_metric_field: str | None = None,
    loan_component: str | None = None,
) -> dict[str, Any]:
    """Build a consistent response for every supported entity."""

    if intent == "loan_lookup":
        metric_field = loan_metric_field
        if metric_field is None:
            rows = data if isinstance(data, list) else [data]
            available_fields = {
                key
                for row in rows
                if isinstance(row, dict)
                for key in row
            }
            metric_field = _loan_metric_field(
                question,
                sorted(available_fields),
            )
        if metric_field:
            answer = loan_amount_response(
                data,
                metric_field,
                loan_component or _loan_component_phrase(question, metric_field),
            )
            show_table = False

    response_text = answer
    if show_table:
        response_text = _table_intro(intent, data, period)
        if answer:
            response_text += f"\n\n{answer}"
    if raw_data is None:
        raw_data = data

    result = {
        "success": True,
        "question": question,
        "answer": response_text,
        "message": response_text,
        "intent": intent,
        "confidence": None,
        "period": period,
        "show_table": show_table,
        "raw_data": raw_data,
        "data": data,
    }
    if show_table and _CAPTURE_COMBINED_ANSWERS.get():
        result["_combined_answer"] = response_text
    return result

def _third_person(answer: str, subject_name: str | None) -> str:
    """When an admin asks about a colleague, speak about that person rather than the requester."""
    if not subject_name or not answer:
        return answer
    first = subject_name.split()[0]
    replacements = [
        (r"\bYou don't have\b", f"{first} doesn't have"),
        (r"\byou don't have\b", f"{first} doesn't have"),
        (r"\bYou have\b", f"{first} has"),
        (r"\byou have\b", f"{first} has"),
        (r"\bYou were\b", f"{first} was"),
        (r"\byou were\b", f"{first} was"),
        (r"\bYou worked\b", f"{first} worked"),
        (r"\byou worked\b", f"{first} worked"),
        (r"\bYou are\b", f"{first} is"),
        (r"\byou are\b", f"{first} is"),
        (r"\bYour\b", f"{first}'s"),
        (r"\byour\b", f"{first}'s"),
        (r"\bYou\b", first),
        (r"\byou\b", first),
    ]
    for pattern, replacement in replacements:
        answer = re.sub(pattern, replacement, answer)
    return answer

def _execute(plan: dict[str, Any], employee_id: int, limit: int, organization_id: int | None = None) -> Any:
    try:
        return execute_query_plan(plan, employee_id=employee_id, limit=limit, organization_id=organization_id)
    except QueryPlanError as exc:
        raise ModelServiceError(f"The query plan failed validation: {exc}") from exc

def _attended_sentence(rows, span, office_only=False):
    """Build an attendance summary from database records."""

    attended_statuses = {"PRESENT", "LATE", "HALF_DAY"}

    matching_rows = [
        row
        for row in rows
        if str(row.get("status") or "").upper() in attended_statuses
        and (
            not office_only
            or str(row.get("work_location") or "").strip().lower() == "office"
        )
    ]

    # Count unique attendance dates rather than accidentally counting
    # duplicate records as separate days.
    daily_statuses = {}
    for row in matching_rows:
        attendance_day = row.get("attendance_date") or row.get("work_date")
        if isinstance(attendance_day, datetime):
            attendance_day = attendance_day.date()
        elif isinstance(attendance_day, str):
            try:
                attendance_day = date.fromisoformat(attendance_day[:10])
            except ValueError:
                continue

        if attendance_day is not None:
            status = str(row.get("status") or "").upper()
            previous = daily_statuses.get(attendance_day)

            # Prefer a late or half-day classification if duplicate
            # records for the same day contain different statuses.
            priority = {"PRESENT": 1, "LATE": 2, "HALF_DAY": 3}
            if previous is None or priority[status] > priority[previous]:
                daily_statuses[attendance_day] = status

    counts = Counter(daily_statuses.values())
    total = len(daily_statuses)
    where = f" {span}" if span else ""

    if total == 0:
        subject = "office attendance records" if office_only else "attendance records"
        return f"I couldn't find any matching {subject}{where}."

    noun = "day" if total == 1 else "days"

    if office_only:
        answer = f"You were recorded as attending the office on {total} {noun}{where}"
    else:
        answer = f"You were recorded as attending on {total} {noun}{where}"

    details = []
    if counts.get("PRESENT"):
        details.append(f"{counts['PRESENT']} marked present")
    if counts.get("LATE"):
        details.append(f"{counts['LATE']} marked late")
    if counts.get("HALF_DAY"):
        details.append(f"{counts['HALF_DAY']} marked half-day")

    if details:
        answer += " (" + ", ".join(details) + ")"

    return answer + "."



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
    return "Your working hours for the requested dates:\n" + "\n".join(lines)


def _hours_sentence(rows, span, overtime):
    field = "overtime_minutes" if overtime else "worked_minutes"
    total = sum(int(row.get(field) or 0) for row in rows)
    hours, minutes = divmod(total, 60)
    name = "overtime" if overtime else "worked time"
    where = f" {span}" if span else ""
    if total == 0:
        return f"Your total {name}{where} was 0 hours and 0 minutes."
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

    # A list of separately named dates is not a continuous range. Fetch the span
    # once and keep only the requested dates, so dates between them are never returned.
    if discrete_dates:
        if len(discrete_dates) > 31:
            return _text_result(
                question,
                "Please ask about 31 dates or fewer at a time.",
                intent="attendance_records",
            )
        wanted = set(discrete_dates)
        span_result = _execute(
            {
                "operation_id": "attendance.list",
                "filters": {
                    "attendance_date": {
                        "gte": min(discrete_dates).isoformat(),
                        "lte": max(discrete_dates).isoformat(),
                    }
                },
                "fields": WORK_LOCATION_FIELDS if asks_work_location else ATTENDANCE_FIELDS,
            },
            employee_id,
            limit=100,
        )
        all_rows = normalize_result_fields("attendance.list", span_result["data"])
        requested_rows = [
            r for r in all_rows
            if (r.get("attendance_date") or r.get("work_date")) in wanted
        ]
        raw_requested_rows = [
            row
            for row in span_result["data"]
            if (row.get("attendance_date") or row.get("work_date")) in wanted
        ]

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
                requested_rows,
                raw_requested_rows,
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
            False, requested_rows, raw_requested_rows)

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
            rows,
            result["data"],
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
            period_out, False, rows, result["data"],
        )
    span = period_phrase(start, end)
    
    q = normalized_question.lower()

    asks_worked_hours = bool(re.search(
        r"\b(?:worked|working|work)\s+hours?\b"
        r"|\bhours?\s+worked\b",
        q,
    ))

    if wants_list and asks_worked_hours:
        display_rows = []

        for row in rows:
            work_date = row.get("attendance_date") or row.get("work_date")
            minutes = row.get("worked_minutes")

            if minutes is None:
                continue

            minutes = int(minutes)
            hours, remainder = divmod(minutes, 60)

            display_rows.append({
                "attendance_date": work_date,
                "worked_hours": f"{hours}h {remainder}m",
            })

        display_rows.sort(
            key=lambda row: str(row["attendance_date"] or "")
        )

        if display_rows:
            answer = f"Your worked hours from {span}:"
        else:
            answer = f"No recorded worked hours were found {span}."

        return _result(
            question,
            answer,
            "attendance_records",
            period_out,
            bool(display_rows),
            display_rows,
            result["data"],
        )

    if ATTENDED_RE.search(normalized_question.lower()):
        office_only = bool(
            re.search(
                r"\b(?:in|at)\s+(?:the\s+)?office\b|\boffice\s+days?\b",
                normalized_question,
                re.IGNORECASE,
            )
        )

        answer = _attended_sentence(
            rows,
            span,
            office_only=office_only,
        )

        return _result(
            question,
            answer,
            "attendance_summary",
            period_out,
            False,
            rows,
            result["data"],
        )

    if SUM_QUESTION_RE.search(normalized_question.lower()):
        return _result(
            question,
            _hours_sentence(
                rows,
                span,
                "overtime" in normalized_question.lower(),
            ),
            "attendance_summary",
            period_out,
            False,
            rows,
            result["data"],
        )

    # Status-filtered questions (e.g. "late") list only matching records.
    status_filter = filters.get("status")
    if not is_single_day and status_filter:
        label = str(status_filter).replace("_", " ").lower()
        if wants_list:
            answer = status_list_answer(rows, start, end, label, tz)
            show_table = bool(rows)
            return _result(
                question,
                answer,
                "attendance_records",
                period_out,
                show_table,
                rows,
                result["data"],
            )
        answer = status_records_answer(rows, span, label)
        return _result(
            question,
            answer,
            "attendance_records",
            period_out,
            False,
            rows,
            result["data"],
        )

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

    return _result(
        question,
        answer,
        "attendance_records",
        period_out,
        show_table,
        rows,
        result["data"],
    )

def _latest_request_sentence(kind: str, rows: list[dict[str, Any]]) -> str:
    """Option 1 wording: name the latest request by start date, its date, and its status."""
    label = "leave request" if kind == "leave" else "work-from-home request"
    latest = max(rows, key=lambda r: as_date(r.get("start_date")) or date.min)
    start = as_date(latest.get("start_date"))
    end = as_date(latest.get("end_date")) or start
    if end and start and end != start:
        when = f"from {fmt_range(start, end)}"
    else:
        when = f"starting {start.day} {start:%B %Y}"
    status = str(latest.get("status") or "unknown").lower().replace("_", " ")
    verb = "is" if status == "pending" else "was"
    return f"Your latest {label}, {when}, {verb} {status}."

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
    if rows and not wants_list and re.search(r"\bstatus\b", normalized_question.lower()):
        return _result(
            question,
            _latest_request_sentence(kind, rows),
            intent,
            period,
            False,
            rows,
            result["data"],
        )
    start, end = as_date(period.get("start_date")), as_date(period.get("end_date"))
    span = period_phrase(start, end)
    answer = request_answer(kind, rows, normalized_question, span, wants_list)
    show_table = wants_list and bool(rows)
    return _result(question, answer, intent, period, show_table, rows, result["data"])


def _answer_holidays(question, normalized_question, plan, period, employee_id, organization_id=None):
    wants_list = question_wants_list(normalized_question)
    is_upcoming = bool(UPCOMING_RE.search(normalized_question.lower()))
    result = _execute(
        {"operation_id": "holiday.list", "filters": dict(plan.get("filters", {}))},
        employee_id,
        limit=100,
        organization_id=organization_id,
    )
    rows = normalize_result_fields("holiday.list", result["data"])
    start, end = as_date(period.get("start_date")), as_date(period.get("end_date"))
    answer = holiday_answer(rows, start, end, wants_list, is_upcoming=is_upcoming)
    show_table = wants_list and bool(rows)
    return _result(question, answer, "holiday_lookup", period, show_table, rows, result["data"])


def _combine_results(question: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    answer = "\n\n".join(
        result.get("_combined_answer", result["answer"])
        for result in results
    )
    show_table = len(results) == 1 and results[0].get("show_table", False)
    return {
        "success": True,
        "question": question,
        "answer": answer,
        "message": answer,
        "intent": results[0]["intent"],
        "confidence": None,
        "period": results[0].get("period", {"start_date": None, "end_date": None}),
        "show_table": show_table,
        "raw_data": [
            {"intent": result.get("intent"), "data": result.get("raw_data")}
            for result in results
        ],
        "data": [
            {"intent": result.get("intent"), "data": result.get("data", [])}
            for result in results
        ],
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
    return _result(question, answer, intent, period, False, rows, result["data"])


def is_third_party_request(question: str) -> bool:
    """True when the question asks about someone other than the logged-in employee."""
    q = question.lower()
    for match in _POSSESSIVE_RE.finditer(q):
        if match.group(1) not in _SELF_POSSESSIVE_EXCLUSIONS:
            return True
    return bool(_THIRD_PARTY_WORDS_RE.search(q))

TEAM_RE = re.compile(
    r"\b(?:team|teams|department|departments|everyone|everybody|"
    r"all\s+employees|organi[sz]ation)\b",
    re.IGNORECASE,
)


def is_team_question(question: str) -> bool:
    # Holiday questions can say "team holiday" or "company holiday"; they are not team views.
    if _HOLIDAY_RE.search(question.lower()):
        return False
    # Salary and payroll questions are never team attendance views.
    if _PAYROLL_RE.search(question):
        return False
    return bool(TEAM_RE.search(question))

def team_attendance_result(
    question: str,
    actor,
    start: date,
    end: date,
) -> dict[str, Any]:
    period = {"start_date": start.isoformat(), "end_date": end.isoformat()}
    span = period_phrase(start, end)
    result = execute_team_summary(actor=actor, start=start, end=end)
    rows = result["rows"]

    if not rows:
        return _result(
            question,
            f"No team members have attendance records {span}.",
            "team_attendance",
            period,
            False,
            [],
        )

    shown = rows[:TEAM_SUMMARY_LIMIT]
    is_org_view = actor.role == SUPER_ADMIN

    table = []
    for row in shown:
        item = {
            "full_name": row["full_name"],
            "employee_code": row["employee_code"],
            "present": row["present"],
            "late": row["late"],
            "absent": row["absent"],
            "half_day": row["half_day"],
        }
        if is_org_view:
            item = {"department": f"Department {row['department_id']}", **item}
        table.append(item)

    if is_org_view:
        answer = f"Your organization has {len(rows)} employees with attendance {span}, grouped by department."
    else:
        answer = f"Your team has {len(rows)} members with attendance {span}."
    if len(rows) > TEAM_SUMMARY_LIMIT:
        answer += (
            f" Showing the first {TEAM_SUMMARY_LIMIT} people. "
            "Name a department or a person to narrow the list."
        )

    return _result(question, answer, "team_attendance", period, True, table, table)


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

    if submitted_basis:
        result = _execute(
            {"operation_id": "timesheet.list",
             "filters": {"submitted_at": {"gte": start.isoformat(), "lte": end.isoformat()}}},
            employee_id, limit=100,
        )
        raw_rows = result["data"]
        rows = raw_rows
    elif start is not None:
        # Timesheet periods are at most seven days, so a period that overlaps the day
        # must start within the six days before it. Overlap is checked in code.
        window_start = start - timedelta(days=6)
        result = _execute(
            {"operation_id": "timesheet.list",
             "filters": {"period_start": {"gte": window_start.isoformat(), "lte": end.isoformat()}}},
            employee_id, limit=100,
        )
        raw_rows = result["data"]
        rows = [row for row in raw_rows if _timesheet_overlaps(row, start, end)]
        raw_rows = rows
    else:
        result = _execute({"operation_id": "timesheet.list", "filters": {}}, employee_id, limit=100)
        raw_rows = result["data"]
        rows = raw_rows

    rows = sorted(rows, key=lambda row: as_date(row.get("period_start")) or date.min, reverse=True)
    structured_rows = normalize_result_fields("timesheet.list", rows)
    raw_rows = sorted(
        raw_rows,
        key=lambda row: as_date(row.get("period_start")) or date.min,
        reverse=True,
    )
    when = period_phrase(start, end) if start is not None else ""

    if not rows:
        if target:
            return _result(question, f"No, I couldn't find any timesheets {when}".rstrip() + ".",
                           "timesheet_lookup", period, False, structured_rows, raw_rows)
        return _result(question, f"I couldn't find any timesheets {when}".rstrip() + ".",
                       "timesheet_lookup", period, False, structured_rows, raw_rows)

    head = rows[0]
    period_start = as_date(head.get("period_start"))
    period_end = as_date(head.get("period_end")) or period_start
    period_text = f"for {fmt_range(period_start, period_end)}" if period_start else "on record"
    status = str(head.get("status") or "unknown").lower().replace("_", " ")
    status_label = TIMESHEET_STATUS_LABELS.get(status, status)
    submitted = as_date(head.get("submitted_at"))
    subject = "your most recent timesheet" if len(rows) > 1 else "your timesheet"

    if target:
        if status == target:
            status_phrase = TIMESHEET_STATUS_PHRASES.get(target, f"is {target}")
            answer = f"Yes, {subject} {period_text} {status_phrase}."
        else:
            answer = f"No, {subject} {period_text} is currently {status_label}."
    else:
        answer = f"{subject.capitalize()} {period_text}"

        if submitted:
            answer += (
                f" was submitted on "
                f"{submitted.day} {submitted:%B %Y}")
            answer += f" and is currently {status_label}."
        else:
            answer += f" is currently {status_label}."

    return _result(
        question, answer, "timesheet_lookup", period, False, structured_rows, raw_rows
    )


def _answer_leave_balance(question, normalized_question, employee_id, today, organization_id=None):
    """Answer leave balance questions from leave_balances, matched to leave types in the database."""
    types_result = _execute(
        {"operation_id": "leave_type.list", "filters": {}},
        employee_id,
        limit=100,
        organization_id=organization_id,
    )
    leave_types = types_result["data"] if isinstance(types_result["data"], list) else []

    year = detect_year(normalized_question, today.year)
    metric = detect_metric(normalized_question)
    selected = match_leave_type(normalized_question, leave_types)

    filters: dict[str, Any] = {"year": year}
    if selected is not None:
        filters["leave_type_id"] = selected["id"]
    balance_result = _execute({"operation_id": "leave_balance.list", "filters": filters}, employee_id, limit=100)
    rows = balance_result["data"] if isinstance(balance_result["data"], list) else []

    answer = answer_leave_balance(rows, leave_types, year, metric, selected,normalized_question)
    show_table = question_wants_list(normalized_question) and bool(rows)
    period = {"start_date": f"{year}-01-01", "end_date": f"{year}-12-31"}
    return _result(
        question,
        answer,
        "leave_balance",
        period,
        show_table,
        enrich_rows(rows, leave_types),
        rows,
    )


@lru_cache(maxsize=1)
def _approved_operations() -> frozenset[str]:
    return frozenset(build_operation_registry(schema_name="public").keys())


def supervisor(question: str) -> str:
    if is_team_question(question):
        return "query"
    """Route the request: 'third_party' is refused, everything else continues."""
    if get_subject() is None and is_third_party_request(question):
        return "third_party"
    return "query"


def resolve_context(question: str) -> str:
    """Normalize the question text. Dates are resolved later, during correction."""
    return correct_typos(question)


def is_approved_operation(operation_id: Any) -> bool:
    return operation_id in _approved_operations()


def direct_answer(
    question: str,
    normalized_question: str,
    employee_id: int,
    organization_id: int | None,
    today: date,
) -> dict[str, Any] | None:
    """Answer leave-type and leave-balance questions before any planning."""
    if (
        _LEAVE_TYPE_LOOKUP_RE.search(normalized_question)
        and _LEAVE_TYPE_AVAILABILITY_RE.search(normalized_question)
        and not re.search(
            r"\b(?:balance|remaining|allocated|used|taken|pending|"
            r"how\s+much|days?\s+(?:left|remaining|used|taken))\b",
            normalized_question,
            re.IGNORECASE,
        )
    ):
        type_result = _execute(
            {"operation_id": "leave_type.list", "filters": {}},
            employee_id,
            limit=100,
            organization_id=organization_id,
        )
        leave_types = (
            type_result["data"]
            if isinstance(type_result.get("data"), list)
            else []
        )
        return _result(
            question,
            leave_type_response(leave_types),
            "leave_type_lookup",
            {"start_date": None, "end_date": None},
            bool(leave_types),
            leave_types,
            type_result["data"],
        )

    actor = get_actor()
    if actor is not None and is_team_question(normalized_question):
        if actor.role not in {ADMIN, SUPER_ADMIN}:
            return _text_result(question, REFUSAL_MESSAGE, intent="access_denied")
        if resolve_date_range_from_question(normalized_question, today) is not None:
            start, end = resolve_date_range_from_question(normalized_question, today)
        else:
            start = today.replace(day=1)
            end = _last_day_of_month(start)
        return team_attendance_result(question, actor, start, end)

    if is_leave_balance_question(normalized_question):
        return _answer_leave_balance(
            question,
            normalized_question,
            employee_id,
            today,
            organization_id=organization_id,
        )

    return None


def plan_question(normalized_question: str) -> dict[str, Any]:
    """Return the raw plan from the model, or the keyword fallback.

    Raises ModelUnavailableError only when the fallback is not an approved operation,
    which matches the previous behavior.
    """
    model_error: ModelServiceError | None = None

    if _is_payroll_query(normalized_question):
        raw_plan = {"operation_id": "payroll_summary.list", "filters": {}}
    else:
        try:
            raw_plan = get_query_plan(normalized_question)
        except ModelServiceError as exc:
            logger.warning("Model plan unavailable, using keyword plan: %s", type(exc).__name__)
            model_error = exc
            raw_plan = rule_based_plan(normalized_question)

    if _is_payroll_query(normalized_question):
        raw_plan = {"operation_id": "payroll_summary.list", "filters": {}}

    status_target = yes_no_status(normalized_question)
    entity = request_entity(normalized_question) if status_target else None
    if entity:
        raw_plan = {"operation_id": f"{entity}.list", "filters": {}}
    logger.debug("operation=%s", raw_plan.get("operation_id"))

    if (
        not is_approved_operation(raw_plan.get("operation_id"))
        and isinstance(model_error, ModelUnavailableError)
    ):
        raise model_error

    return raw_plan


def correct_plan(
    raw_plan: dict[str, Any],
    question: str,
    normalized_question: str,
    employee_id: int,
    organization_id: int | None,
    today: date,
) -> tuple[dict[str, Any], dict[str, str | None]]:
    """Correct the plan with code, then apply identity and field rules."""
    loan_values = None
    if raw_plan.get("operation_id", "").startswith("loan_request."):
        loan_values = _loan_value_catalog(employee_id, organization_id)
    plan, period = normalize_and_correct_plan(
        raw_plan, normalized_question, today, loan_values=loan_values
    )

    if plan.get("operation_id", "").startswith("task."):
        q = normalized_question.lower()
        task_filters = dict(plan.get("filters", {}))
        for field in ("assigned_to_employee_id", "managed_by_employee_id"):
            value = task_filters.get(field)
            if isinstance(value, str) and value.strip().lower() in {
                "me", "myself", "my", "current user",
            }:
                task_filters.pop(field, None)
        identity_field = _task_identity_filter(q)
        if identity_field:
            task_filters[identity_field] = employee_id
        plan["filters"] = task_filters

    if plan.get("operation_id", "").startswith("loan_request."):
        loan_filters = dict(plan.get("filters", {}))
        loan_metric = (
            plan.get("aggregate_field")
            if plan.get("operation_id") == "loan_request.sum"
            else _loan_metric_field(normalized_question, plan.get("fields", []))
        )
        component_phrase = _loan_component_phrase(normalized_question, loan_metric)

        if "component" not in loan_filters and (component_phrase or loan_metric):
            component_result = _execute(
                {
                    "operation_id": "loan_request.list",
                    "fields": ["component"],
                    "filters": {
                        key: value
                        for key, value in loan_filters.items()
                        if key != "component"
                    },
                },
                employee_id,
                limit=100,
                organization_id=organization_id,
            )
            components = {
                " ".join(str(row.get("component") or "").split())
                for row in component_result.get("data", [])
                if isinstance(row, dict) and row.get("component")
            }
            matching_component = next(
                (
                    component
                    for component in sorted(components, key=len, reverse=True)
                    if re.search(
                        r"(?<!\w)" + re.escape(component) + r"(?!\w)",
                        normalized_question,
                        re.IGNORECASE,
                    )
                ),
                None,
            )
            selected_component = matching_component or component_phrase
            if selected_component:
                loan_filters["component"] = selected_component

        plan["filters"] = loan_filters

    if plan.get("operation_id") == "task.list":
        task_fields = build_operation_registry().get("task.list", {}).get("fields", [])
        field_phrases = {
            "title": ("title", "task name"),
            "project_id": ("project", "project id"),
            "task_date": ("task date", "due date"),
            "description": ("description",),
            "start_time": ("start time",),
            "end_time": ("end time",),
            "status": ("status",),
            "assigned_to_employee_id": ("assignee", "assigned to"),
            "managed_by_employee_id": ("manager", "managed by"),
            "performance_score": ("performance score",),
        }
        requested_fields = [
            field
            for field in task_fields
            if any(
                re.search(
                    r"(?<!\w)" + re.escape(phrase).replace(r"\ ", r"\s+") + r"(?!\w)",
                    normalized_question,
                    re.IGNORECASE,
                )
                for phrase in field_phrases.get(field, ())
            )
        ]
        default_task_fields = [
            field for field in ("title", "status", "task_date") if field in task_fields
        ]
        q = normalized_question.lower()
        asks_assigned_to_self = bool(
            re.search(r"\b(?:assigned|assigned\s+to)\s+me\b", q)
        )
        asks_managed_by_self = bool(
            re.search(
                r"\b(?:managed|manage|managing)\s+by\s+me\b"
                r"|\b(?:what|which)\s+tasks?\s+(?:am\s+i\s+)?managing\b",
                q,
            )
        )
        selected_fields = list(default_task_fields)
        if asks_assigned_to_self:
            selected_fields.append("assigned_to_employee_id")
        if asks_managed_by_self:
            selected_fields.append("managed_by_employee_id")
        for field in requested_fields:
            if field not in selected_fields:
                selected_fields.append(field)
        plan["fields"] = [field for field in selected_fields if field in task_fields]

    return plan, period


def validate_plan(plan: dict[str, Any]) -> tuple[str, str | None]:
    """Return ('ok', None) or ('missing_info', question). Rules are added in a later step."""
    return "ok", None


def run_llm_chat(
    question: str,
    employee_id: int,
    organization_id: int | None = None,
) -> dict[str, Any]:
    """Orchestrate the stages in the same order as before the split."""
    parts = split_compound_question(question)
    if len(parts) > 1:
        with _capture_combined_answers():
            results = [
                run_llm_chat(part, employee_id, organization_id)
                for part in parts
            ]
        return _combine_results(question, results)

    if supervisor(question) == "third_party":
        return _text_result(question, REFUSAL_MESSAGE, intent="access_denied")

    normalized_question = resolve_context(question)
    today = get_current_date()

    direct = direct_answer(question, normalized_question, employee_id, organization_id, today)
    if direct is not None:
        return direct

    raw_plan = plan_question(normalized_question)
    if not is_approved_operation(raw_plan.get("operation_id")):
        return _text_result(question, UNSUPPORTED_MESSAGE, intent="unsupported")

    try:
        plan, period = correct_plan(
            raw_plan, question, normalized_question, employee_id, organization_id, today,
        )
    except InvalidDateError as exc:
        answer = (
            f"'{exc}' is not a valid date. Please check the day and month, "
            "for example: 19 October 2026."
        )
        return _text_result(question, answer, intent="attendance_records")

    try:
        return execute_and_format(
            question,
            normalized_question,
            plan,
            period,
            employee_id,
            organization_id,
            today,
            yes_no_status(normalized_question),
        )
    except AccessDenied:
        return _text_result(question, REFUSAL_MESSAGE, intent="access_denied")


def execute_and_format(
    question: str,
    normalized_question: str,
    plan: dict[str, Any],
    period: dict[str, Any],
    employee_id: int,
    organization_id: int | None,
    today: date,
    status_target: str | None,
) -> dict[str, Any]:
    """Execute the approved plan and format the answer."""
    operation_id = plan["operation_id"]

    if operation_id == "attendance.list":
        return _answer_attendance(question, normalized_question, plan, period, employee_id)

    if operation_id in {"leave_request.list", "wfh_request.list"}:
        if status_target:
            return _answer_status_check(question, normalized_question, plan, period, employee_id, status_target)
        return _answer_requests(question, normalized_question, plan, period, employee_id)
    if operation_id == "holiday.list":
        return _answer_holidays(question, normalized_question, plan, period, employee_id, organization_id)
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

    asks_single_payroll_metric = bool(
        operation_id == "payroll_summary.list"
        and period.get("start_date") is None
        and re.search(
            r"\b(?:gross|net|deduct\w*|take[- ]home|credited)\b",
            normalized_question.lower(),
        )
        and not re.search(
            r"\b(?:total|sum|highest|lowest|maximum|minimum|"
            r"history|all|every|each|list|show)\b",
            normalized_question.lower(),
        )
    )

    query_result = _execute(
        execution_plan,
        employee_id,
        limit=1 if asks_latest_timesheet or asks_single_payroll_metric else 100 if asks_pending_timesheets else 50,
        organization_id=organization_id,
    )
    if asks_pending_timesheets:
        query_result["data"] = [
            row for row in query_result.get("data", [])
            if str(row.get("status") or "").strip().lower() in {"draft", "submitted"}
        ]

    operation = query_result["operation"]
    entity = query_result["entity"]
    raw_data = query_result["data"]
    data = normalize_result_fields(operation_id, raw_data)

    operation_to_intent = {
        "attendance.count": "attendance_summary",
        "attendance.sum": "attendance_summary",
        "attendance.group_by": "attendance_summary",
        "timesheet.list": "timesheet_lookup",
        "timesheet.count": "timesheet_lookup",
        "timesheet.group_by": "timesheet_lookup",
        "holiday.count": "holiday_lookup",
        "work_schedule.list": "schedule_lookup",
        "leave_request.count": "leave_status",
        "wfh_request.count": "wfh_status",
        "leave_balance.list": "leave_balance",
        "leave_balance.count": "leave_balance",
        "leave_balance.sum": "leave_balance",
        "leave_balance.group_by": "leave_balance",
        "leave_type.list": "leave_type_lookup",
        "leave_type.count": "leave_type_lookup",
        "payroll_summary.list": "payroll_lookup",
        "task.list": "task_lookup",
        "task.count": "task_lookup",
        "task.sum": "task_lookup",
        "task.group_by": "task_lookup",
        "loan_request.list": "loan_lookup",
        "loan_request.count": "loan_lookup",
        "loan_request.sum": "loan_lookup",
    }
    intent = operation_to_intent.get(operation_id, "attendance_records")
    if intent is None:
        return _text_result(question, UNSUPPORTED_MESSAGE, intent="unsupported")

    if operation == "count":
        count = data.get("count", 0) if isinstance(data, dict) else 0
        status_filter = (
            plan.get("filters", {}).get("loan_status")
            or plan.get("filters", {}).get("status")
        )
        span = period_phrase(as_date(period.get("start_date")), as_date(period.get("end_date")))
        if operation_id == "task.count":
            answer = task_count_response(
                int(count),
                plan.get("filters", {}),
                normalized_question,
                span,
                employee_id,
            )
        else:
            answer = count_response(
                entity=entity,
                count=int(count),
                status=status_filter,
                span=span,
                filters=plan.get("filters", {}),
        question=normalized_question,
    )
        return _result(question, answer, intent, period, False, data, raw_data)

    if operation == "group_by":
        rows = data if isinstance(data, list) else []
        span = period_phrase(as_date(period.get("start_date")), as_date(period.get("end_date")))
        group_by_field = plan.get("group_by_field")
        if entity == "attendance" and ATTENDED_RE.search(normalized_question.lower()):
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
            return _result(question, answer, intent, period, False, data, raw_data)
        group_labels = None
        if entity == "leave_balance" and group_by_field == "leave_type_id":
            type_result = _execute(
                {"operation_id": "leave_type.list", "filters": {}},
                employee_id,
                limit=100,
                organization_id=organization_id,
            )
            group_labels = {
                row.get("id"): str(row.get("name") or row.get("code") or "Leave type")
                for row in type_result.get("data", [])
                if isinstance(row, dict)
            }
        answer = grouped_response(
            entity,
            rows,
            group_by_field,
            plan.get("aggregate_function"),
            plan.get("aggregate_field"),
            span,
            group_labels,
        )
        return _result(question, answer, intent, period, False, data, raw_data)

    if operation == "sum":
        field = data.get("field", "value") if isinstance(data, dict) else "value"
        total = data.get("total") if isinstance(data, dict) else None
        span = period_phrase(as_date(period.get("start_date")), as_date(period.get("end_date")))
        if operation_id == "loan_request.sum":
            answer = loan_amount_response(
                data,
                field,
                plan.get("filters", {}).get("component"),
                span,
            )
            return _result(question, answer, intent, period, False, data, raw_data)
        answer = sum_response(field, total, span)
        return _result(question, answer, intent, period, False, data, raw_data)

    if operation_id == "leave_balance.list":
        return _answer_leave_balance(
            question,
            normalized_question,
            employee_id,
            today,
            organization_id=organization_id,
        )

    if operation_id == "payroll_summary.list":
        message = _payroll_response(
            data,
            period,
            normalized_question,
        )
        # Specific metric questions return a concise answer without a table.
        asks_specific_metric = bool(
            re.search(
                r"\b(?:deductions?|deductible|deductibles|"
                r"tax(?:es)?\s+deducted|"
                r"deduction\s+amount|"
                r"deducted(?:\s+(?:amount|from|for))?|"
                r"net\s+(?:amount|salary|pay|income)|"
                r"take[- ]home\s+(?:pay|salary|amount)|"
                r"amount\s+(?:received|credited)|"
                r"gross\s+(?:amount|salary|pay|earnings)|"
                r"earnings\s+before\s+deductions)\b",
                normalized_question.lower(),
            )
        )
        show_payroll_table = (
            isinstance(data, list)
            and bool(data)
            and not asks_specific_metric
        )
        return _result(
            question,
            message,
            "payroll_lookup",
            period,
            show_payroll_table,
            data if isinstance(data, list) else [],
            raw_data,
        )

    if operation_id == "timesheet.list":
        timesheet_rows = data if isinstance(data, list) else []
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

    elif operation_id == "loan_request.list":
        loan_metric = _loan_metric_field(
            normalized_question,
            plan.get("fields", []),
        )
        if loan_metric:
            message = loan_amount_response(
                data,
                loan_metric,
                plan.get("filters", {}).get("component"),
                period_phrase(
                    as_date(period.get("start_date")),
                    as_date(period.get("end_date")),
                ),
            )
            return _result(question, message, intent, period, False, data, raw_data)

        applied = {
            key: value
            for key, value in plan.get("filters", {}).items()
            if key in LOAN_VALUE_FIELDS and isinstance(value, str)
        }
        if applied:
            return _result(
                question,
                _describe_loan_matches(data, applied),
                intent,
                period,
                False,
                data,
                raw_data,
            )

        message = (
            "Your matching records are listed below."
            if data
            else "No matching records were found."
        )

    elif operation_id == "leave_type.list":
        message = leave_type_response(data if isinstance(data, list) else [])

    elif isinstance(data, list):
        message = "Your matching records are listed below." if data else "No matching records were found."
    else:
        message = "Your requested information was retrieved."

    return _result(
        question,
        message,
        intent,
        period,
        isinstance(data, list) and bool(data),
        data,
        raw_data,
    )