
# from datetime import date, timedelta
# from functools import lru_cache
# from threading import Lock
# import re

# from ai_model.predict import load_model, process_question
# from backend.repositories.attendance_repository import (
#     get_attendance_records,
#     get_attendance_summary,
# )
# from backend.repositories.calendar_repository import (
#     get_holidays,
#     get_work_schedules,
# )
# from backend.repositories.leave_repository import get_leave_requests
# from backend.repositories.timesheet_repository import get_timesheets
# from backend.repositories.wfh_repository import get_wfh_requests
# from backend.services.response_formatter import format_chat_response


# @lru_cache(maxsize=1)
# def get_model_components():
#     """Load the model, tokenizer, and intent definitions once per process."""
#     return load_model()


# # In-memory conversation state. This is suitable for local development and a
# # single backend process. Use Redis/PostgreSQL for multi-worker/production use.
# _SESSION_STATE: dict[tuple[str, int], dict] = {}
# _SESSION_LOCK = Lock()
# _SESSION_MAX_AGE_TURNS = 6


# def _is_short_clarification_reply(question: str) -> bool:
#     """Recognize concise parameter replies without enumerating domain questions."""
#     text = question.strip().lower()
#     if len(text.split()) > 8:
#         return False
#     return bool(re.search(
#         r"\\b(today|yesterday|this week|this month|last month|"
#         r"january|february|march|april|may|june|july|august|september|"
#         r"october|november|december|\\d{4}-\\d{2}-\\d{2}|"
#         r"\\d{1,2}[/-]\\d{1,2}(?:[/-]\\d{2,4})?)\\b",
#         text,
#     ))


# def _get_session(session_id: str | None, employee_id: int) -> tuple[str | None, dict | None]:
#     if not session_id:
#         return None, None
#     key = (session_id, employee_id)
#     with _SESSION_LOCK:
#         state = _SESSION_STATE.get(key)
#         if state and state.get("turns_left", 0) <= 0:
#             _SESSION_STATE.pop(key, None)
#             state = None
#         return session_id, state


# def _save_session(session_id: str | None, employee_id: int, state: dict | None) -> None:
#     if not session_id:
#         return
#     key = (session_id, employee_id)
#     with _SESSION_LOCK:
#         if state is None:
#             _SESSION_STATE.pop(key, None)
#         else:
#             state["turns_left"] = _SESSION_MAX_AGE_TURNS
#             _SESSION_STATE[key] = state


# def resolve_period(
#     period: str | None,
#     today: date,
# ) -> tuple[date, date] | None:
#     """Resolve supported relative periods into inclusive date ranges."""

#     if period is None:
#         return None

#     if period == "today":
#         return today, today

#     if period == "yesterday":
#         yesterday = today - timedelta(days=1)
#         return yesterday, yesterday

#     if period == "this_week":
#         # Monday through Sunday.
#         start = today - timedelta(days=today.weekday())
#         return start, start + timedelta(days=6)

#     if period == "this_month":
#         start = today.replace(day=1)

#         if today.month == 12:
#             next_month = date(today.year + 1, 1, 1)
#         else:
#             next_month = date(today.year, today.month + 1, 1)

#         return start, next_month - timedelta(days=1)

#     if period == "last_month":
#         this_month_start = today.replace(day=1)
#         last_month_end = this_month_start - timedelta(days=1)
#         last_month_start = last_month_end.replace(day=1)

#         return last_month_start, last_month_end

#     return None


# def get_date_range(request, today: date) -> tuple[date, date] | None:
#     """Resolve explicit dates, a single date, or a relative period."""

#     if request.start_date is not None and request.end_date is not None:
#         return request.start_date, request.end_date

#     if request.on_date is not None:
#         return request.on_date, request.on_date

#     return resolve_period(request.period, today)


# def failure_response(
#     message: str,
#     intent: str | None = None,
#     confidence: float | None = None,
#     details: list | None = None,
# ) -> dict:
#     """Return a consistent error response with a readable answer."""

#     result = {
#         "success": False,
#         "message": message,
#     }

#     if intent is not None:
#         result["intent"] = intent

#     if confidence is not None:
#         result["confidence"] = round(confidence, 4)

#     if details is not None:
#         result["details"] = details

#     return format_chat_response(result)


# def run_chat(question: str, employee_id: int, session_id: str | None = None) -> dict:
#     """
#     Classify a question, validate extracted parameters, retrieve authorized
#     employee data through repositories, and format a grounded response.

#     employee_id must come from the API layer after employee validation.
#     The model must never generate or execute SQL.
#     """

#     question = question.strip()

#     if not question:
#         return failure_response("Please enter a question.")

#     # 1. Load the custom-trained intent model.
#     model, tokenizer, intents = get_model_components()

#     # 2. If the previous turn asked for a missing parameter, combine a concise
#     #    reply (for example, "this month") with the original question. Session
#     #    state is isolated by both session_id and employee_id.
#     effective_question = question
#     _, previous_state = _get_session(session_id, employee_id)
#     if (
#         previous_state
#         and previous_state.get("pending_question")
#         and _is_short_clarification_reply(question)
#     ):
#         effective_question = (
#             f"{previous_state['pending_question']} {question}"
#         )

#     # 3. Predict the intent and extract parameters from the complete request.
#     intent, confidence, parsed = process_question(
#         effective_question,
#         model,
#         tokenizer,
#         intents,
#     )
    
#     if intent == "out_of_scope":
#         return failure_response(
#             message=(
#                 "I'm Tickora AI, your attendance management assistant. "
#                 "I can help with attendance, attendance summaries, "
#                 "leave requests, timesheets, holidays, work schedules, "
#                 "and work-from-home requests."
#             ),
#             intent=intent,
#             confidence=confidence,
#         )

#     # 3. Handle parameter-extraction or validation failures.
#     if isinstance(parsed, dict) and "error" in parsed:
#         return failure_response(
#             message=(
#                 "I couldn't identify all the required details. "
#                 "Please rephrase your question or specify the date."
#             ),
#             intent=intent,
#             confidence=confidence,
#             details=parsed.get("details", []),
#         )

#     request = parsed
#     today = date.today()

#     # The previous clarification is now being resolved; it will be replaced
#     # below if this request still needs a required parameter.
#     _save_session(session_id, employee_id, None)

#     # 4. Resolve date filters.
#     date_range = get_date_range(request, today)

#     start_date = date_range[0] if date_range else None
#     end_date = date_range[1] if date_range else None

#     # 5. Require a date range for period-based queries.
#     if request.intent in {
#         "attendance_records",
#         "attendance_summary",
#         "timesheet_lookup",
#     } and date_range is None:
#         _save_session(
#             session_id,
#             employee_id,
#             {"pending_question": effective_question},
#         )
#         return failure_response(
#             message=(
#                 "Please specify a period, such as today, this month, "
#                 "last month, or a date range."
#             ),
#             intent=request.intent,
#             confidence=confidence,
#         )

#     if request.intent == "holiday_lookup" and date_range is None:
#         _save_session(
#             session_id,
#             employee_id,
#             {"pending_question": effective_question},
#         )
#         return failure_response(
#             message=(
#                 "Please specify when you want to check holidays, "
#                 "such as this month or a specific date."
#             ),
#             intent=request.intent,
#             confidence=confidence,
#         )

#     # 6. Route the validated request to the correct repository.
#     if request.intent == "attendance_records":
#         records = get_attendance_records(
#             employee_id,
#             start_date,
#             end_date,
#         )

#         if request.status:
#             records = [
#                 row
#                 for row in records
#                 if str(row.get("status", "")).upper()
#                 == request.status
#             ]

#         data = records

#     elif request.intent == "attendance_summary":
#         data = get_attendance_summary(
#             employee_id,
#             start_date,
#             end_date,
#         )

#     elif request.intent == "timesheet_lookup":
#         records = get_timesheets(
#             employee_id,
#             start_date,
#             end_date,
#         )

#         if request.status:
#             records = [
#                 row
#                 for row in records
#                 if str(row.get("submission_status", "")).upper()
#                 == request.status
#             ]

#         data = records

#     elif request.intent == "leave_status":
#         data = get_leave_requests(
#             employee_id,
#             start_date,
#             end_date,
#             request.status,
#         )

#     elif request.intent == "wfh_status":
#         data = get_wfh_requests(
#             employee_id,
#             start_date,
#             end_date,
#             request.status,
#         )

#     elif request.intent == "holiday_lookup":
#         data = get_holidays(
#             start_date,
#             end_date,
#             request.region,
#         )

#     elif request.intent == "schedule_lookup":
#         schedule_date = request.on_date

#         if schedule_date is None and request.period in {
#             "today",
#             "yesterday",
#         }:
#             resolved_range = resolve_period(request.period, today)
#             if resolved_range is not None:
#                 schedule_date = resolved_range[0]

#         if schedule_date is None:
#             return failure_response(
#                 message="Please specify the date for your work schedule.",
#                 intent=request.intent,
#                 confidence=confidence,
#             )

#         data = get_work_schedules(
#             employee_id,
#             schedule_date,
#         )

#     else:
#         # Never dispatch an unsupported intent.
#         return failure_response(
#             message="This request type is not supported.",
#             intent=intent,
#             confidence=confidence,
#         )

#     # 7. Construct a status message based on the actual query result.
#     if isinstance(data, list) and not data:
#         message = (
#             "No matching records were found for the requested criteria."
#         )

#     elif request.intent == "attendance_summary":
#         message = (
#             f"Attendance summary from {start_date} to {end_date} retrieved."
#         )

#     elif isinstance(data, list):
#         message = f"Found {len(data)} matching record(s)."

#     else:
#         message = "Your requested information was retrieved."

#     # 8. Format the response for the user while preserving structured data.
#     result = {
#         "success": True,
#         "message": message,
#         "intent": request.intent,
#         "confidence": round(confidence, 4),
#         "requested_metric": request.requested_metric,
#         "status": request.status,
#         "period": {
#             "start_date": (
#                 start_date.isoformat() if start_date else None
#             ),
#             "end_date": (
#                 end_date.isoformat() if end_date else None
#             ),
#         },
#         "data": data,
#     }

#     return format_chat_response(result)


from datetime import date, timedelta
from functools import lru_cache
from threading import Lock
import re

from ai_model.predict import load_model, process_question
from backend.repositories.attendance_repository import (
    get_attendance_records,
    get_attendance_summary,
)
from backend.repositories.calendar_repository import (
    get_holidays,
    get_work_schedules,
)
from backend.repositories.leave_repository import get_leave_requests
from backend.repositories.timesheet_repository import get_timesheets
from backend.repositories.wfh_repository import get_wfh_requests
from backend.services.response_formatter import format_chat_response


@lru_cache(maxsize=1)
def get_model_components():
    """Load the model, tokenizer, and intent definitions once per process."""
    return load_model()


# In-memory conversation state. This is suitable for local development and a
# single backend process. Use Redis/PostgreSQL for multi-worker/production use.
_SESSION_STATE: dict[tuple[str, int], dict] = {}
_SESSION_LOCK = Lock()
_SESSION_MAX_AGE_TURNS = 6


def _is_short_clarification_reply(question: str) -> bool:
    """Recognize concise parameter replies without enumerating domain questions."""
    text = question.strip().lower()
    if len(text.split()) > 8:
        return False
    return bool(re.search(
        r"\b(today|yesterday|this week|this month|last month|"
        r"january|february|march|april|may|june|july|august|september|"
        r"october|november|december|\d{4}-\d{2}-\d{2}|"
        r"\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\b",
        text,
    ))


def _get_session(session_id: str | None, employee_id: int) -> tuple[str | None, dict | None]:
    if not session_id:
        return None, None
    key = (session_id, employee_id)
    with _SESSION_LOCK:
        state = _SESSION_STATE.get(key)
        if state and state.get("turns_left", 0) <= 0:
            _SESSION_STATE.pop(key, None)
            state = None
        return session_id, state


def _save_session(session_id: str | None, employee_id: int, state: dict | None) -> None:
    if not session_id:
        return
    key = (session_id, employee_id)
    with _SESSION_LOCK:
        if state is None:
            _SESSION_STATE.pop(key, None)
        else:
            state["turns_left"] = _SESSION_MAX_AGE_TURNS
            _SESSION_STATE[key] = state


def resolve_period(
    period: str | None,
    today: date,
) -> tuple[date, date] | None:
    """Resolve supported relative periods into inclusive date ranges."""

    if period is None:
        return None

    if period == "today":
        return today, today

    if period == "yesterday":
        yesterday = today - timedelta(days=1)
        return yesterday, yesterday

    if period == "this_week":
        # Monday through Sunday.
        start = today - timedelta(days=today.weekday())
        return start, start + timedelta(days=6)

    if period == "this_month":
        start = today.replace(day=1)

        if today.month == 12:
            next_month = date(today.year + 1, 1, 1)
        else:
            next_month = date(today.year, today.month + 1, 1)

        return start, next_month - timedelta(days=1)

    if period == "last_month":
        this_month_start = today.replace(day=1)
        last_month_end = this_month_start - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)

        return last_month_start, last_month_end

    return None


def get_date_range(request, today: date) -> tuple[date, date] | None:
    """Resolve explicit dates, a single date, or a relative period."""

    if request.start_date is not None and request.end_date is not None:
        return request.start_date, request.end_date

    if request.on_date is not None:
        return request.on_date, request.on_date

    return resolve_period(request.period, today)


def failure_response(
    message: str,
    intent: str | None = None,
    confidence: float | None = None,
    details: list | None = None,
) -> dict:
    """Return a consistent error response with a readable answer."""

    result = {
        "success": False,
        "message": message,
    }

    if intent is not None:
        result["intent"] = intent

    if confidence is not None:
        result["confidence"] = round(confidence, 4)

    if details is not None:
        result["details"] = details

    return format_chat_response(result)


def run_chat(question: str, employee_id: int, session_id: str | None = None) -> dict:
    """
    Classify a question, validate extracted parameters, retrieve authorized
    employee data through repositories, and format a grounded response.

    employee_id must come from the API layer after employee validation.
    The model must never generate or execute SQL.
    """

    question = question.strip()

    if not question:
        return failure_response("Please enter a question.")

    # 1. Load the custom-trained intent model.
    model, tokenizer, intents = get_model_components()

    # 2. If the previous turn asked for a missing parameter, combine a concise
    #    reply (for example, "this month") with the original question. Session
    #    state is isolated by both session_id and employee_id.
    effective_question = question
    _, previous_state = _get_session(session_id, employee_id)
    is_contextual_follow_up = bool(
        previous_state
        and previous_state.get("pending_question")
        and _is_short_clarification_reply(question)
    )
    if is_contextual_follow_up:
        effective_question = f"{previous_state['pending_question']} {question}"

    # 3. Parse the full request. For a clarification reply, preserve the intent
    #    that originally required clarification; a short reply such as "today"
    #    must not be routed as a brand-new question by itself.
    intent, confidence, parsed = process_question(
        effective_question,
        model,
        tokenizer,
        intents,
    )
    if (
        is_contextual_follow_up
        and previous_state.get("pending_intent")
        and not (isinstance(parsed, dict) and "error" in parsed)
    ):
        intended_intent = previous_state["pending_intent"]
        if hasattr(parsed, "model_copy"):
            parsed = parsed.model_copy(update={"intent": intended_intent})
        elif isinstance(parsed, dict):
            parsed = {**parsed, "intent": intended_intent}
        else:
            try:
                parsed.intent = intended_intent
            except (AttributeError, TypeError):
                pass
        intent = intended_intent
    
    if intent == "out_of_scope":
        return failure_response(
            message=(
                "I'm Tickora AI, your attendance management assistant. "
                "I can help with attendance, attendance summaries, "
                "leave requests, timesheets, holidays, work schedules, "
                "and work-from-home requests."
            ),
            intent=intent,
            confidence=confidence,
        )

    # 3. Handle parameter-extraction or validation failures.
    if isinstance(parsed, dict) and "error" in parsed:
        return failure_response(
            message=(
                "I couldn't identify all the required details. "
                "Please rephrase your question or specify the date."
            ),
            intent=intent,
            confidence=confidence,
            details=parsed.get("details", []),
        )

    request = parsed
    today = date.today()

    # The previous clarification is now being resolved; it will be replaced
    # below if this request still needs a required parameter.
    _save_session(session_id, employee_id, None)

    # 4. Resolve date filters.
    date_range = get_date_range(request, today)

    start_date = date_range[0] if date_range else None
    end_date = date_range[1] if date_range else None

    # 5. Require a date range for period-based queries.
    if request.intent in {
        "attendance_records",
        "attendance_summary",
        "timesheet_lookup",
    } and date_range is None:
        _save_session(
            session_id,
            employee_id,
            {"pending_question": effective_question, "pending_intent": request.intent},
        )
        return failure_response(
            message=(
                "Please specify a period, such as today, this month, "
                "last month, or a date range."
            ),
            intent=request.intent,
            confidence=confidence,
        )

    if request.intent == "holiday_lookup" and date_range is None:
        _save_session(
            session_id,
            employee_id,
            {"pending_question": effective_question, "pending_intent": request.intent},
        )
        return failure_response(
            message=(
                "Please specify when you want to check holidays, "
                "such as this month or a specific date."
            ),
            intent=request.intent,
            confidence=confidence,
        )

    # 6. Route the validated request to the correct repository.
    if request.intent == "attendance_records":
        records = get_attendance_records(
            employee_id,
            start_date,
            end_date,
        )

        if request.status:
            records = [
                row
                for row in records
                if str(row.get("status", "")).upper()
                == request.status
            ]

        data = records

    elif request.intent == "attendance_summary":
        data = get_attendance_summary(
            employee_id,
            start_date,
            end_date,
        )

    elif request.intent == "timesheet_lookup":
        records = get_timesheets(
            employee_id,
            start_date,
            end_date,
        )

        if request.status:
            records = [
                row
                for row in records
                if str(row.get("submission_status", "")).upper()
                == request.status
            ]

        data = records

    elif request.intent == "leave_status":
        data = get_leave_requests(
            employee_id,
            start_date,
            end_date,
            request.status,
        )

    elif request.intent == "wfh_status":
        data = get_wfh_requests(
            employee_id,
            start_date,
            end_date,
            request.status,
        )

    elif request.intent == "holiday_lookup":
        data = get_holidays(
            start_date,
            end_date,
            request.region,
        )

    elif request.intent == "schedule_lookup":
        schedule_date = request.on_date

        if schedule_date is None and request.period in {
            "today",
            "yesterday",
        }:
            resolved_range = resolve_period(request.period, today)
            if resolved_range is not None:
                schedule_date = resolved_range[0]

        if schedule_date is None:
            return failure_response(
                message="Please specify the date for your work schedule.",
                intent=request.intent,
                confidence=confidence,
            )

        data = get_work_schedules(
            employee_id,
            schedule_date,
        )

    else:
        # Never dispatch an unsupported intent.
        return failure_response(
            message="This request type is not supported.",
            intent=intent,
            confidence=confidence,
        )

    # 7. Construct a status message based on the actual query result.
    if isinstance(data, list) and not data:
        message = (
            "No matching records were found for the requested criteria."
        )

    elif request.intent == "attendance_summary":
        message = (
            f"Attendance summary from {start_date} to {end_date} retrieved."
        )

    elif isinstance(data, list):
        message = f"Found {len(data)} matching record(s)."

    else:
        message = "Your requested information was retrieved."

    # 8. Format the response for the user while preserving structured data.
    result = {
        "success": True,
        "message": message,
        "intent": request.intent,
        "confidence": round(confidence, 4),
        "requested_metric": request.requested_metric,
        "status": request.status,
        "period": {
            "start_date": (
                start_date.isoformat() if start_date else None
            ),
            "end_date": (
                end_date.isoformat() if end_date else None
            ),
        },
        "data": data,
    }

    return format_chat_response(result)
