import re
from datetime import date
from functools import lru_cache
from typing import Any

from backend.config import get_settings
# from sqlalchemy import exc
from backend.agents.state import ChatState
from backend.services.date_resolver import (
    InvalidDateError,
    MONTHS,
    resolve_date_spec,
)
from backend.services.llm_chat_service import (
    UNSUPPORTED_MESSAGE,
    _capture_combined_answers,
    _combine_results,
    _text_result,
    correct_plan,
    direct_answer,
    execute_and_format,
    get_current_date,
    has_data_concept,
    is_approved_operation,
    is_directory_question,
    is_team_question,
    plan_question,
    resolve_context,
    should_refuse_third_party_request,
    split_compound_question,
    validate_plan,
    yes_no_status,
    out_of_scope_message,
    _HOLIDAY_RE,
    ModelServiceError
)
from backend.security.access_policy import AccessDenied, REFUSAL_MESSAGE, get_actor, SUPER_ADMIN
from backend.services.operation_registry import build_operation_registry
from backend.services.payload.builders import (
    PayloadError, build_count, build_group_by, build_sum,
)
from backend.services.payload.entities import build_specs
from sqlalchemy.exc import SQLAlchemyError

import logging
logger = logging.getLogger(__name__)

GREETING_RE = re.compile(
    r"^\s*(?:hi|hello|hey|howdy|greetings|good\s+morning|good\s+afternoon"
    r"|good\s+evening|good\s+night)(?:\s+there)?[!,.?\s]*$",
    re.IGNORECASE,
)

GREETING_EXTRA_RE = re.compile(
    r"^\s*(?:thanks|thank you|bye|goodbye|help|what can you do)[!.?\s]*$",
    re.IGNORECASE,
)

RETRIEVAL_OPENER_RE = re.compile(
    r"^\s*(?:what|which|who|when|where|how|why|is|are|was|were|do|does|did|"
    r"have|has|can\s+i|could\s+i|show|list|display|give\s+me|get|"
    r"tell\s+me\s+(?:my|the)|my|i\s+want\s+to\s+see)\b",
    re.IGNORECASE,
)

DATE_HINT_RE = re.compile(
    r"\b(?:january|february|march|april|may|june|july|august|september|"
    r"october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\b"
    r"|\b(?:19|20)\d{2}\b",
    re.IGNORECASE,
)

DATA_CONCEPT_RE = re.compile(
    r"\b(?:attendance|attend\w*|clock|check[- ]?(?:in|out)|punch|late|absent|absences?|present|"
    r"half[- ]day|overtime|worked|hours?|leaves?|balance|wfh|work\s+from\s+home|"
    r"holidays?|timesheets?|tasks?|payroll|pay|paid|salary|salaries|net|gross|"
    r"payslips?|payslip|deductions?|deducted|loans?|installments?|schedule|"
    r"performance\s+score|status|pending|approved|rejected|submitted|draft|"
    r"records?|requests?|apply|applied|credited|office|miss|days?|"
    r"half[- ]days?|diwali|festival|holiday)\b",
    re.IGNORECASE,
)

WRITE_RE = re.compile(
    r"^\s*(?:(?:please|can you|could you|would you|i want to|i need to)\s+)*"
    r"(?:delete|remove|cancel|update|change|edit|modify|approve|reject|submit|apply|create|add)\b",
    re.IGNORECASE,
)

CREATIVE_RE = re.compile(
    r"\b(?:poem|poetry|story|stories|joke|song|essay|limerick|haiku|rap)\b",
    re.IGNORECASE,
)

def is_read_shape(question: str) -> bool:
    """A read request opens with a question or a retrieval verb. Anything else is not a read."""
    return bool(RETRIEVAL_OPENER_RE.search(question))

WRITE_MESSAGE = (
    "I can only show information from your records. I can't change, add, "
    "cancel, or approve anything. Please use the HR system to make changes."
)

FOLLOWUP_RE = re.compile(
    r"^\s*(?:what|how)\s+about\b|^\s*(?:and|also|same)\b",
    re.IGNORECASE,
)
FOLLOWUP_CLARIFY = (
    "Please ask the full question, including the topic, for example "
    "'Show my records for November'."
)

PERIOD_WORDS = {
    *MONTHS,
    "and", "at", "between", "current", "during", "first", "for", "from",
    "in", "last", "month", "of", "on", "past", "previous", "second",
    "the", "this", "third", "through", "thru", "till", "to", "today",
    "fourth", "until", "week", "year", "yesterday", "st", "nd", "rd", "th",
}

settings = get_settings()

NARRATABLE_INTENTS = {
    "attendance_records", "attendance_summary", "leave_status", "wfh_status",
    "timesheet_lookup", "holiday_lookup", "leave_balance", "leave_type_lookup",
}


@lru_cache(maxsize=1)
def _entity_specs() -> dict:
    return build_specs(build_operation_registry(schema_name="public"))

from backend.services.answer_router import choose_route
from backend.services.payload.answer_payload import compute_facts
from backend.services.answer_writer import write_answer, passes_answer_check
import json

def _route_answer(question, result, plan, period):
    if not settings.llm_narration_enabled:
        return result
    if choose_route(result) == "table":
        return result
    payload = compute_facts(question, plan, period, result)
    facts = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    logger.warning("facts: %s", facts)
    try:
        answer = write_answer(question, payload)
    except Exception:
        logger.exception("LLM answer failed; using template")
        return result
    if passes_answer_check(answer, payload):
        result["answer"] = answer
        result["message"] = answer
    else:
        logger.warning("answer rejected; template kept: %r", answer)
    return result


def _payload_for(plan: dict, period: dict, result: dict) -> dict | None:
    """Build a payload from the rows already returned. Returns None when no builder applies."""
    spec = _entity_specs().get("attendance")
    start, end = period.get("start_date"), period.get("end_date")
    if spec is None or not start or not end:
        return None

    s, e = date.fromisoformat(start), date.fromisoformat(end)
    op = plan.get("operation_id")
    filters = plan.get("filters") or {}
    data = result.get("data")

    try:
        if op == "attendance.count" and isinstance(data, dict) and "count" in data:
            return build_count(spec, data["count"], s, e, filters)

        if op == "attendance.list" and isinstance(data, list):
            field = plan.get("aggregate_field")
            if field in {"worked_minutes", "overtime_minutes"}:
                total = sum(int(r.get(field) or 0) for r in data)
                return build_sum(spec, field, total, s, e, filters)
            if filters.get("status"):
                return build_count(spec, len(data), s, e, filters)

        if op == "attendance.group_by" and isinstance(data, list):
            return build_group_by(spec, data, s, e, filters)
    except PayloadError:
        return None

    return None


def _maybe_narrate(question: str, result: dict, plan: dict, period: dict) -> dict:
    payload = _payload_for(plan, period, result)
    logger.warning(
        "narration: op=%s flag=%s payload=%s intent=%s",
        plan.get("operation_id"), settings.llm_narration_enabled,
        payload is not None, result.get("intent"),
    )
    if not settings.llm_narration_enabled or payload is None:
        return result
    if result.get("show_table") or result.get("intent") not in NARRATABLE_INTENTS:
        return result
    result["answer"] = narrate(question, payload, result["answer"])
    result["message"] = result["answer"]
    return result


def _is_period_only_followup(question: str) -> bool:
    tokens = re.findall(r"[a-z]+|\d+", question.lower())
    if not tokens or any(
        not token.isdigit() and token not in PERIOD_WORDS for token in tokens
    ):
        return False
    try:
        return resolve_date_spec(question, get_current_date()) is not None
    except InvalidDateError:
        return True


def _is_followup(question: str, last_operation: str | None) -> bool:
    return bool(FOLLOWUP_RE.search(question)) or (
        bool(last_operation)
        and is_approved_operation(last_operation)
        and _is_period_only_followup(question)
    )

def supervisor_node(state: ChatState) -> dict[str, Any]:
    logger.debug("GRAPH PATH: %s", state["question"])
    question = resolve_context(state["question"])
    if GREETING_RE.fullmatch(question) or GREETING_EXTRA_RE.fullmatch(question):
        return {"request_type": "greeting"}
    if WRITE_RE.search(question):
        return {"request_type": "write_request"}
    if CREATIVE_RE.search(question):
        return {"request_type": "out_of_scope"}
    actor = get_actor()
    if (
        actor is not None
        and actor.role != SUPER_ADMIN
        and re.search(r"\b(?:company|organi[sz]ation|every\s+employee|all\s+employees?)\b", question, re.IGNORECASE)
        and not _HOLIDAY_RE.search(question)
    ):
        return {"request_type": "third_party"}
    if is_team_question(question) or is_directory_question(question):
        return {"request_type": "query"}
    if not (
        _is_followup(question, state.get("last_operation"))
        or DATA_CONCEPT_RE.search(question)
        or (is_read_shape(question) and has_data_concept(question))
    ):
        return {"request_type": "out_of_scope"}
    if len(split_compound_question(question)) > 1:
        return {"request_type": "compound"}
    if should_refuse_third_party_request(question):
        return {"request_type": "third_party"}
    return {"request_type": "query"}


def greeting_node(state: ChatState) -> dict[str, Any]:
    from backend.main import get_greeting_response

    current_employee = {
        "employee_id": state["employee_id"],
        "employee_code": state["employee_code"],
        "organization_id": state["organization_id"],
        "full_name": None,
    }
    return {"result": get_greeting_response(state["question"], current_employee)}


def context_node(state: ChatState) -> dict[str, Any]:
    normalized = resolve_context(state["question"])
    update: dict[str, Any] = {"normalized_question": normalized}
    direct = direct_answer(
        state["question"], normalized, state["employee_id"],
        state["organization_id"], get_current_date(),
    )
    if direct is not None:
        update["result"] = direct
        return update
    last_operation = state.get("last_operation")
    if _is_followup(normalized, last_operation):
        if last_operation and is_approved_operation(last_operation):
            # Reuse the operation the previous answer used; the new period is set by correction.
            update["raw_plan"] = {"operation_id": last_operation, "filters": {}}
        else:
            update["result"] = _text_result(state["question"], FOLLOWUP_CLARIFY, "unsupported")
    return update


def route_after_context(state: ChatState) -> str:
    if "result" in state:
        return "done"
    if "raw_plan" in state:
        return "correct"
    return "plan"

def planning_node(state: ChatState) -> dict[str, Any]:
    return {"raw_plan": plan_question(state["normalized_question"])}

from backend.security.access_policy import get_actor
from backend.services.payload.entities import can_access_entity
from backend.services.response_writer import narrate

def correction_node(state: ChatState) -> dict[str, Any]:
    raw_operation = state["raw_plan"].get("operation_id")

    if not is_approved_operation(raw_operation):
        logger.warning("Plan operation not approved: %r", raw_operation)
        return {"status": "invalid", "clarification": None}

    actor = get_actor()
    raw_entity = str(raw_operation or "").split(".", 1)[0]
    if actor is not None and not can_access_entity(raw_entity, actor.role):
        logger.warning("Blocked %s for role %s before correction", raw_entity, actor.role)
        return {
            "status": "access_denied",
            "clarification": None,
            "result": _text_result(state["question"], REFUSAL_MESSAGE, "access_denied"),
        }

    try:
        plan, period = correct_plan(
            state["raw_plan"], state["question"], state["normalized_question"],
            state["employee_id"], state["organization_id"], get_current_date(),
        )
    except InvalidDateError as exc:
        return {
            "status": "invalid",
            "clarification": str(exc),
            "result": _text_result(
                state["question"],
                f"'{exc}' is not a valid date. Please check the day and month, "
                "for example: 19 October 2026.",
                "attendance_records",
            ),
        }
    status, reason = validate_plan(plan)
    return {"plan": plan, "period": period, "status": status, "clarification": reason}

def execution_node(state: ChatState) -> dict[str, Any]:
    actor = get_actor()
    entity = str(state["plan"].get("operation_id", "")).split(".", 1)[0]
    if actor is not None and not can_access_entity(entity, actor.role):
        return {"result": _text_result(state["question"], REFUSAL_MESSAGE, "access_denied")}
    try:
        result = execute_and_format(
            state["question"], state["normalized_question"], state["plan"], state["period"],
            state["employee_id"], state["organization_id"], get_current_date(),
            yes_no_status(state["normalized_question"]),
        )
        result["operation_id"] = state["plan"].get("operation_id")
    except AccessDenied:
        result = _text_result(state["question"], REFUSAL_MESSAGE, "access_denied")
    except ModelServiceError:
        result = _text_result(state["question"], UNSUPPORTED_MESSAGE, "unsupported")
    except SQLAlchemyError:
        logger.exception("Query failed for plan operation")
        result = _text_result(
            state["question"],
            "I couldn't read that information right now. Please try again or rephrase the question.",
            "unsupported",
        )

    result = _route_answer(state["question"], result, state["plan"], state["period"])
    return {"result": result}

def error_node(state: ChatState) -> dict[str, Any]:
    if state.get("request_type") == "write_request":
        return {"result": _text_result(state["question"], WRITE_MESSAGE, "unsupported")}
    if state.get("request_type") == "third_party":
        return {"result": _text_result(state["question"], REFUSAL_MESSAGE, "access_denied")}
    if state.get("request_type") == "out_of_scope":
        return {"result": _text_result(state["question"], out_of_scope_message(), "unsupported")}
    if state.get("clarification") is not None:
        return {"result": _text_result(
            state["question"],
            f"'{state['clarification']}' is not a valid date. Please check the day and month, "
            "for example: 19 October 2026.",
            "attendance_records",
        )}
    return {"result": _text_result(state["question"], UNSUPPORTED_MESSAGE, "unsupported")}


def route_request(state: ChatState) -> str:
    return state["request_type"]

def route_validation(state: ChatState) -> str:
    return state["status"]

def compound_node(state: ChatState) -> dict[str, Any]:
    from backend.agents.graph import get_chat_graph

    graph = get_chat_graph()
    base = {k: state[k] for k in ("session_id", "employee_id", "employee_code", "organization_id")}
    results = []
    with _capture_combined_answers():
        for part in split_compound_question(state["question"]):
            out = graph.invoke({**base, "question": part})
            results.append(out["result"])
    return {"result": _combine_results(state["question"], results)}