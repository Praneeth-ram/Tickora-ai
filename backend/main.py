from datetime import date
from fastapi import FastAPI, HTTPException, Query, Depends
from backend.dependencies.auth import get_current_employee
from sqlalchemy import text
from backend.db import engine
from backend.repositories.attendance_repository import (
    get_attendance_records,
    get_attendance_summary,
)

from backend.repositories.timesheet_repository import get_timesheets
from backend.repositories.leave_repository import get_leave_requests
from backend.repositories.wfh_repository import get_wfh_requests
from backend.repositories.calendar_repository import (
    get_holidays,
    get_work_schedules,
)

from pydantic import BaseModel, Field
from fastapi.encoders import jsonable_encoder
from backend.services.chat_service import run_chat
from fastapi.middleware.cors import CORSMiddleware
from backend.services.auth_service import (
    verify_password,
    create_access_token,
)
import os
from backend.services.llm_chat_service import (
    run_llm_chat,
    ModelServiceError,
)

app = FastAPI(
    title="Tickora AI API",
    description="Attendance data API for the Tickora assistant",
    version="0.1.0",
)

# Add CORS middleware to allow frontend to call this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # React dev server
        "http://localhost:5174",
        # Add any other origins (e.g., deployed frontend URL)
    ],
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

def find_employee_id(employee_code: str) -> int:
    # Resolve a sample employee code to its database ID.
    query = text("""
        SELECT employee_id
        FROM public.employees
        WHERE employee_code = :employee_code
          AND is_active = TRUE
    """)

    with engine.connect() as connection:
        employee_id = connection.execute(
            query,
            {"employee_code": employee_code},
        ).scalar_one_or_none()

    if employee_id is None:
        raise HTTPException(
            status_code=404,
            detail="Active employee not found",
        )

    return employee_id

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
def login(body: LoginRequest):
    email = body.email.strip().lower()
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
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password",
        )

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
    return {"status": "ok", "service": "tickora-ai"}

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

    try:
        records = get_leave_requests(
            employee_id, start_date, end_date, status
        )
        return {
            "employee_code": current_employee["employee_code"],
            "records": records,
        }
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=str(exc)
        ) from exc

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

    try:
        records = get_wfh_requests(
            employee_id, start_date, end_date, status
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    if not records:
        if status:
            message = (
                f"No WFH requests found with status '{status}' "
                "for the selected date range."
            )
        else:
            message = (
                "No WFH requests found for the selected date range."
            )

        raise HTTPException(
            status_code=404,
            detail=message,
        )

    return {
        "employee_code": current_employee["employee_code"],
        "records": records,
    }

@app.get("/api/holidays")
def holidays(
    start_date: date = Query(...),
    end_date: date = Query(...),
    region: str | None = None,
):
    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="start_date cannot be after end_date",
        )

    records = get_holidays(start_date, end_date, region)
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


@app.post("/api/chat/{employee_code}")
def chat_with_tickora(
    employee_code: str,
    body: ChatRequest,
    current_employee: dict = Depends(get_current_employee),
):
    employee_id = require_matching_employee(
        employee_code,
        current_employee,
    )

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
            result = run_chat(
                question=body.question.strip(),
                employee_id=employee_id,
                session_id=body.session_id,
            )

        return jsonable_encoder(result)

    except ModelServiceError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
