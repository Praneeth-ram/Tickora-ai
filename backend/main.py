from datetime import date
from fastapi import FastAPI, HTTPException, Query
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


app = FastAPI(
    title="Tickora AI API",
    description="Attendance data API for the Tickora assistant",
    version="0.1.0",
)

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


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "tickora-ai"}


@app.get("/api/attendance/{employee_code}")
def attendance_records(
    employee_code: str,
    start_date: date = Query(...),
    end_date: date = Query(...),
):
    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="start_date cannot be after end_date",
        )

    employee_id = find_employee_id(employee_code)

    records = get_attendance_records(
        employee_id, start_date, end_date
    )

    return {
        "employee_code": employee_code,
        "start_date": start_date,
        "end_date": end_date,
        "records": records,
    }

@app.get("/api/attendance/{employee_code}/summary")
def attendance_summary(
    employee_code: str,
    start_date: date = Query(...),
    end_date: date = Query(...),
):
    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="start_date cannot be after end_date",
        )

    employee_id = find_employee_id(employee_code)

    summary = get_attendance_summary(
        employee_id, start_date, end_date
    )

    return {
        "employee_code": employee_code,
        "start_date": start_date,
        "end_date": end_date,
        "summary": summary,
    }


@app.get("/api/timesheets/{employee_code}")
def timesheets(
    employee_code: str,
    start_date: date = Query(...),
    end_date: date = Query(...),
):
    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="start_date cannot be after end_date",
        )

    employee_id = find_employee_id(employee_code)
    records = get_timesheets(employee_id, start_date, end_date)

    return {
        "employee_code": employee_code,
        "records": records,
    }


@app.get("/api/leave/{employee_code}")
def leave_requests(
    employee_code: str,
    start_date: date | None = None,
    end_date: date | None = None,
    status: str | None = None,
):
    try:
        employee_id = find_employee_id(employee_code)
        records = get_leave_requests(
            employee_id, start_date, end_date, status
        )
        return {"employee_code": employee_code, "records": records}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/wfh/{employee_code}")
def wfh_requests(
    employee_code: str,
    start_date: date | None = None,
    end_date: date | None = None,
    status: str | None = None,
):
    try:
        employee_id = find_employee_id(employee_code)
        records = get_wfh_requests(
            employee_id, start_date, end_date, status
        )
        return {"employee_code": employee_code, "records": records}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
):
    employee_id = find_employee_id(employee_code)
    records = get_work_schedules(employee_id, on_date)

    return {
        "employee_code": employee_code,
        "on_date": on_date,
        "records": records,
    }
