from contextlib import asynccontextmanager
from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import FastAPI, HTTPException, Query, Depends, Request
from backend.config import get_settings
from backend.dependencies.auth import get_current_employee
from sqlalchemy import text
from backend.db import engine
from backend.security.access_policy import load_actor, set_actor, reset_actor
from backend.repositories.attendance_repository import (
    get_attendance_records,
)
from backend.repositories.timesheet_repository import get_timesheets
from backend.repositories.leave_repository import get_leave_requests
from backend.repositories.wfh_repository import get_wfh_requests
from backend.repositories.calendar_repository import (
    get_holidays,
    get_work_schedules,
)
from pydantic import BaseModel, Field
from backend.services import model_inference
from backend.errors import register_exception_handlers
from backend.exceptions import ServiceUnavailableError
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from backend.services.auth_service import (
    verify_password,
    create_access_token,
)
import os
from backend.services.llm_chat_service import (
    _text_result,
    run_llm_chat,
    ModelServiceError,
)
import re
from backend.services.date_resolver import validate_date_range
import logging
from backend.services.login_rate_limiter import LoginRateLimiter, login_limiter
from backend.security.access_policy import set_subject, reset_subject
from backend.security.subject_resolution import NOT_FOUND_MESSAGE, load_non_person_phrases, resolve_subject, names_a_person
from backend.services.login_rate_limiter import LoginRateLimiter, login_limiter

chat_limiter = LoginRateLimiter(max_attempts=30, window_seconds=60)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the model once per process. If it cannot load, the API still starts
    # and chat answers 503 until the problem is fixed and the server restarted.
    try:
        model_inference.load_model()
    except Exception:
        logger.exception("Tickora model failed to load; chat is unavailable.")
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Tickora AI API",
    description="Attendance data API for the Tickora assistant",
    version="0.1.0",
)

from backend.security.audit_log import configure_audit_logger
configure_audit_logger()

register_exception_handlers(app)
logger = logging.getLogger(__name__)

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

# Add CORS middleware to allow frontend to call this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods (GET, POST, OPTIONS, etc.)
    allow_headers=["*"],  # Allow all headers
)

class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    # Stable per-chat identifier so clarification replies retain context.
    session_id: str = Field(min_length=1, max_length=100)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)

# EMPLOYEE_CODE_RE = re.compile(r"\bEMP\d+\b", re.IGNORECASE)

# def names_other_employee(question: str, own_code: str) -> bool:
#     """True when the question names an employee code other than the caller's."""
#     own = own_code.strip().upper()
#     return any(
#         match.group(0).upper() != own
#         for match in EMPLOYEE_CODE_RE.finditer(question)
#     )


def require_matching_employee(
    requested_employee_code: str,
    current_employee: dict,
) -> int:
    if (
        requested_employee_code.strip().upper()
        != current_employee["employee_code"].upper()
    ):
        raise HTTPException(
            status_code=403,
            detail="You cannot access another employee's data",
        )

    return current_employee["employee_id"]

@app.post("/api/auth/login")
def login(body: LoginRequest, request: Request):
    email = body.email.strip().lower()
    client_ip = request.client.host if request.client else "unknown"
    ip_key = f"ip:{client_ip}"
    email_key = f"email:{email}"

    login_limiter.check(ip_key)
    login_limiter.check(email_key)

    query = text("""
    SELECT
        e.id AS employee_id,
        e.organization_id,
        e.employee_code,
        e.full_name,
        e.email,
        c.password_hash
    FROM public.employees AS e
    JOIN public.employee_credentials AS c
        ON c.employee_id = e.id
    WHERE LOWER(e.email) = :email
      AND e.is_active = TRUE
      AND c.is_enabled = TRUE
    """)

    with engine.connect() as connection:
        employee = connection.execute(
            query,
            {"email": email},
        ).mappings().one_or_none()

    if employee is None or not verify_password(
        body.password, employee["password_hash"]
    ):
        login_limiter.record_failure(ip_key)
        login_limiter.record_failure(email_key)
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password",
        )

    login_limiter.reset(email_key)

    token = create_access_token(
        employee_id=employee["employee_id"],
        employee_code=employee["employee_code"],
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "employee": {
            "employee_id": employee["employee_id"],
            "employee_code": employee["employee_code"],
            "full_name": employee["full_name"],
            "email": employee["email"],
        },
    }

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "model_loaded": model_inference.is_loaded(),
    }


@app.get("/v1/models")
def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": "tickora-ai",
                "object": "model",
                "created": int(datetime.now().timestamp()),
                "owned_by": "tickora",
            }
        ],
    }


@app.get("/api/attendance/{employee_code}")
def attendance_records(
    employee_code: str,
    start_date: date = Query(...),
    end_date: date = Query(...),
    current_employee: dict = Depends(get_current_employee),
):
    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="start_date cannot be after end_date",
        )

    validate_date_range(start_date, end_date)

    employee_id = require_matching_employee(
        employee_code, current_employee
    )

    records = get_attendance_records(
        employee_id, start_date, end_date
    )

    return {
        "employee_code": current_employee["employee_code"],
        "start_date": start_date,
        "end_date": end_date,
        "records": records,
    }

@app.get("/api/timesheets/{employee_code}")
def timesheets(
    employee_code: str,
    start_date: date = Query(...),
    end_date: date = Query(...),
    current_employee: dict = Depends(get_current_employee),
):
    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="start_date cannot be after end_date",
        )

    validate_date_range(start_date, end_date)

    employee_id = require_matching_employee(
        employee_code, current_employee
    )
    records = get_timesheets(employee_id, start_date, end_date)

    return {
        "employee_code": current_employee["employee_code"],
        "records": records,
    }

@app.get("/api/leave/{employee_code}")
def leave_requests(
    employee_code: str,
    start_date: date | None = None,
    end_date: date | None = None,
    status: str | None = None,
    current_employee: dict = Depends(get_current_employee),
):
    employee_id = require_matching_employee(
        employee_code, current_employee
    )
    
    if start_date is not None and end_date is not None:   # NEW
        validate_date_range(start_date, end_date) 

    records = get_leave_requests(
        employee_id, start_date, end_date, status
    )
    return {
        "employee_code": current_employee["employee_code"],
        "records": records,
    }

@app.get("/api/wfh/{employee_code}")
def wfh_requests(
    employee_code: str,
    start_date: date | None = None,
    end_date: date | None = None,
    status: str | None = None,
    current_employee: dict = Depends(get_current_employee),
):
    employee_id = require_matching_employee(
        employee_code, current_employee
    )

    if start_date is not None and end_date is not None:   # NEW
        validate_date_range(start_date, end_date) 

    records = get_wfh_requests(
        employee_id, start_date, end_date, status
    )

    message = None
    if not records:
        message = (
            f"No WFH requests found with status '{status}' for the selected date range."
            if status
            else "No WFH requests found for the selected date range."
        )

    return {
        "employee_code": current_employee["employee_code"],
        "records": records,
        "message": message,
    }

@app.get("/api/holidays")
def holidays(
    start_date: date = Query(...),
    end_date: date = Query(...),
    region: str | None = None,
    current_employee: dict = Depends(get_current_employee),
):
    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="start_date cannot be after end_date",
        )

    validate_date_range(start_date, end_date)

    records = get_holidays(
        start_date,
        end_date,
        region,
        organization_id=current_employee["organization_id"],
    )
    return {"records": records}

@app.get("/api/schedules/{employee_code}")
def work_schedules(
    employee_code: str,
    on_date: date = Query(...),
    current_employee: dict = Depends(get_current_employee),
):
    employee_id = require_matching_employee(
        employee_code, current_employee
    )
    records = get_work_schedules(employee_id, on_date)

    return {
        "employee_code": current_employee["employee_code"],
        "on_date": on_date,
        "records": records,
    }

def get_greeting_response(question: str, current_employee: dict) -> dict | None:
    """Respond to standalone greetings without invoking the query planner."""

    greeting_pattern = re.compile(
        r"^\s*(?:hi|hello|hey|howdy|greetings|"
        r"good\s+morning|good\s+afternoon|good\s+evening|good\s+night)"
        r"(?:\s+there)?[!,.?\s]*$",
        re.IGNORECASE,
    )

    # Only handle a standalone greeting.
    # Questions such as "Hi, what is my salary?" must continue normally.
    if not greeting_pattern.fullmatch(question):
        return None

    employee_name = current_employee.get("full_name")

    # If the authentication dependency doesn't provide the name,
    # retrieve it using the authenticated employee's ID and code.
    if not employee_name:
        query = text("""
            SELECT full_name
            FROM public.employees
            WHERE id = :employee_id
              AND employee_code = :employee_code
              AND is_active = TRUE
        """)

        with engine.connect() as connection:
            employee_name = connection.execute(
                query,
                {
                    "employee_id": current_employee["employee_id"],
                    "employee_code": current_employee["employee_code"],
                },
            ).scalar_one_or_none()

    first_name = str(employee_name or "there").strip().split()[0]

    timezone_name = os.getenv(
        "APP_TIMEZONE",
        os.getenv("TICKORA_TIMEZONE", "Asia/Kolkata"),
    )
    
    try:
        hour = datetime.now(ZoneInfo(timezone_name)).hour
    except ZoneInfoNotFoundError:
        hour = datetime.now().hour

    if 5 <= hour < 12:
        greeting = "Good morning"
    elif 12 <= hour < 17:
        greeting = "Good afternoon"
    elif 17 <= hour < 21:
        greeting = "Good evening"
    else:
        greeting = "Hello"

    answer = f"{greeting}, {first_name}! How can I help you today?"

    return {
        "success": True,
        "question": question,
        "answer": answer,
        "message": answer,
        "intent": "greeting",
        "confidence": None,
        "period": {"start_date": None, "end_date": None},
        "show_table": False,
        "raw_data": None,
        "data": [],
    }

@app.post("/api/chat/{employee_code}")
def chat_with_tickora(
    employee_code: str,
    body: ChatRequest,
    current_employee: dict = Depends(get_current_employee),
):
    employee_id = require_matching_employee(employee_code, current_employee)
    chat_limiter.hit(f"chat:{employee_id}")
    with engine.connect() as connection:
        actor = load_actor(connection, employee_id, current_employee["employee_code"])
        subject_id = resolve_subject(connection, actor, body.question)
        non_person = load_non_person_phrases(connection, actor.organization_id)
        if subject_id is None and names_a_person(body.question, actor, non_person):
            return jsonable_encoder(
                _text_result(body.question, NOT_FOUND_MESSAGE, intent="unsupported")
            )
    token = set_actor(actor)
    subject_token = set_subject(subject_id) if subject_id is not None else None
    try:
        return _chat(body, employee_id, current_employee)
    finally:
        if subject_token is not None:
            reset_subject(subject_token)
        reset_actor(token)

def _localize(result: dict) -> dict:
    from backend.security.access_policy import get_subject, subject_name
    from backend.services.llm_chat_service import _third_person

    subject_id = get_subject()
    if subject_id is None:
        return result
    with engine.connect() as connection:
        name = subject_name(connection, subject_id)
    for key in ("answer", "message"):
        if isinstance(result.get(key), str):
            result[key] = _third_person(result[key], name)
    return result

def _chat(
    body: ChatRequest,
    employee_id: int,
    current_employee: dict,
):
    # if names_other_employee(body.question, current_employee["employee_code"]):
    #     return jsonable_encoder(
    #         _text_result(body.question, THIRD_PARTY_MESSAGE, intent="unsupported")
    #     )
    
    # employee_id = require_matching_employee(
    #     employee_code,
    #     current_employee,
    # )
    greeting_result = get_greeting_response(
        body.question.strip(),
        current_employee,
    )
    if greeting_result is not None:
        return jsonable_encoder(greeting_result)

    organization_id = current_employee.get("organization_id")
    if organization_id is None:
        with engine.connect() as connection:
            organization_id = connection.execute(
                text("""
                    SELECT organization_id
                    FROM public.employees
                    WHERE id = :employee_id
                      AND employee_code = :employee_code
                      AND is_active = TRUE
                """),
                {
                    "employee_id": employee_id,
                    "employee_code": current_employee["employee_code"],
                },
            ).scalar_one_or_none()
    if organization_id is None:
        raise HTTPException(
            status_code=403,
            detail="Authenticated organization could not be verified.",
        )

    if get_settings().agent_orchestration:
        from backend.agents.graph import get_chat_graph

        state = get_chat_graph().invoke({
            "question": body.question.strip(),
            "session_id": body.session_id,
            "employee_id": employee_id,
            "employee_code": current_employee["employee_code"],
            "organization_id": organization_id,
        })
        return jsonable_encoder(_localize(state["result"]))

    try:
        use_llm = os.getenv(
            "TICKORA_LLM_CHAT_ENABLED", "true"
        ).lower() == "true"

        if use_llm:
            organization_id = current_employee.get("organization_id")

            # Resolve organization scope from PostgreSQL if the
            # authentication dependency does not already include it.
            if organization_id is None:
                with engine.connect() as connection:
                    organization_id = connection.execute(
                        text("""
                            SELECT organization_id
                            FROM public.employees
                            WHERE id = :employee_id
                              AND employee_code = :employee_code
                              AND is_active = TRUE
                        """),
                        {
                            "employee_id": employee_id,
                            "employee_code": current_employee["employee_code"],
                        },
                    ).scalar_one_or_none()

            if organization_id is None:
                raise HTTPException(
                    status_code=403,
                    detail="Authenticated organization could not be verified.",
                )

            result = run_llm_chat(
                question=body.question.strip(),
                employee_id=employee_id,
                organization_id=organization_id,
            )

        else:
            raise ServiceUnavailableError("Chat is currently disabled.")

        return jsonable_encoder(_localize(result))

    except ModelServiceError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc
