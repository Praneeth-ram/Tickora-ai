import re
from typing import Any
from backend.agents.state import ChatState
from backend.services.date_resolver import InvalidDateError
from backend.services.llm_chat_service import (
    THIRD_PARTY_MESSAGE,
    UNSUPPORTED_MESSAGE,
    _combine_results,
    _text_result,
    correct_plan,
    direct_answer,
    execute_and_format,
    get_current_date,
    is_approved_operation,
    is_third_party_request,
    plan_question,
    resolve_context,
    split_compound_question,
    validate_plan,
    yes_no_status,
)

import logging
logger = logging.getLogger(__name__)

GREETING_RE = re.compile(
    r"^\s*(?:hi|hello|hey|howdy|greetings|good\s+morning|good\s+afternoon"
    r"|good\s+evening|good\s+night)(?:\s+there)?[!,.?\s]*$",
    re.IGNORECASE,
)


def supervisor_node(state: ChatState) -> dict[str, Any]:
    logger.info("GRAPH PATH: %s", state["question"])
    question = state["question"]
    if GREETING_RE.fullmatch(question):
        return {"request_type": "greeting"}
    if len(split_compound_question(question)) > 1:
        return {"request_type": "compound"}
    if is_third_party_request(question):
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


def planning_node(state: ChatState) -> dict[str, Any]:
    return {"raw_plan": plan_question(state["normalized_question"])}


def correction_node(state: ChatState) -> dict[str, Any]:
    if not is_approved_operation(state["raw_plan"].get("operation_id")):
        return {"status": "invalid", "clarification": None}
    try:
        plan, period = correct_plan(
            state["raw_plan"], state["question"], state["normalized_question"],
            state["employee_id"], state["organization_id"], get_current_date(),
        )
    except InvalidDateError as exc:
        return {"status": "invalid", "clarification": str(exc)}
    status, reason = validate_plan(plan)
    return {"plan": plan, "period": period, "status": status, "clarification": reason}


def execution_node(state: ChatState) -> dict[str, Any]:
    return {"result": execute_and_format(
        state["question"], state["normalized_question"], state["plan"], state["period"],
        state["employee_id"], state["organization_id"], get_current_date(),
        yes_no_status(state["normalized_question"]),
    )}


def clarification_node(state: ChatState) -> dict[str, Any]:
    return {"result": _text_result(state["question"], state["clarification"], "clarification")}


def error_node(state: ChatState) -> dict[str, Any]:
    if state.get("request_type") == "third_party":
        return {"result": _text_result(state["question"], THIRD_PARTY_MESSAGE, "unsupported")}
    if state.get("status") == "invalid" and state.get("clarification"):
        return {"result": _text_result(
            state["question"],
            f"'{state['clarification']}' is not a valid date. Please check the day and month, "
            "for example: 19 October 2026.",
            "attendance_records",
        )}
    return {"result": _text_result(state["question"], UNSUPPORTED_MESSAGE, "unsupported")}


def route_request(state: ChatState) -> str:
    return state["request_type"]


def route_after_context(state: ChatState) -> str:
    return "done" if "result" in state else "plan"


def route_validation(state: ChatState) -> str:
    return state["status"]

def compound_node(state: ChatState) -> dict[str, Any]:
    from backend.agents.graph import get_chat_graph

    graph = get_chat_graph()
    base = {k: state[k] for k in ("session_id", "employee_id", "employee_code", "organization_id")}
    results = []
    for part in split_compound_question(state["question"]):
        out = graph.invoke({**base, "question": part})
        results.append(out["result"])
    return {"result": _combine_results(state["question"], results)}