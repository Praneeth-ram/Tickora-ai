import re
from typing import Any

# from sqlalchemy import exc
from backend.agents.state import ChatState
from backend.security.access_policy import get_subject
from backend.services.date_resolver import InvalidDateError
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
    is_third_party_request,
    plan_question,
    resolve_context,
    split_compound_question,
    validate_plan,
    yes_no_status,
    out_of_scope_message,
    ModelServiceError
)
from backend.security.access_policy import AccessDenied, REFUSAL_MESSAGE
from sqlalchemy.exc import SQLAlchemyError

import logging
logger = logging.getLogger(__name__)

GREETING_RE = re.compile(
    r"^\s*(?:hi|hello|hey|howdy|greetings|good\s+morning|good\s+afternoon"
    r"|good\s+evening|good\s+night)(?:\s+there)?[!,.?\s]*$",
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

WRITE_RE = re.compile(
    r"^\s*(?:(?:please|can you|could you|would you|i want to|i need to)\s+)*"
    r"(?:delete|remove|cancel|update|change|edit|modify|approve|reject|submit|apply|create|add)\b",
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

def supervisor_node(state: ChatState) -> dict[str, Any]:
    logger.debug("GRAPH PATH: %s", state["question"])
    question = state["question"]
    if GREETING_RE.fullmatch(question):
        return {"request_type": "greeting"}
    if WRITE_RE.search(question):
        return {"request_type": "write_request"}
    if is_team_question(question) or is_directory_question(question):
        return {"request_type": "query"}
    if not (
        FOLLOWUP_RE.search(question)
        or (is_read_shape(question) and has_data_concept(question))
        or (has_data_concept(question) and DATE_HINT_RE.search(question))
    ):
        return {"request_type": "out_of_scope"}
    if len(split_compound_question(question)) > 1:
        return {"request_type": "compound"}
    if get_subject() is None and is_third_party_request(question):
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
    if FOLLOWUP_RE.search(normalized):
        last_operation = state.get("last_operation")
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


def correction_node(state: ChatState) -> dict[str, Any]:
    if not is_approved_operation(state["raw_plan"].get("operation_id")):
        logger.warning("Plan operation not approved: %r", state["raw_plan"].get("operation_id"))
        return {"status": "invalid", "clarification": None}
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