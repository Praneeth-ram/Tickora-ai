from datetime import date
from sqlalchemy import text
from backend.db import engine

def get_timesheets(
    employee_id: int,
    start_date: date,
    end_date: date,
) -> list[dict]:
    # Retrieve an employee's timesheets for a date range.

    if start_date > end_date:
        raise ValueError("start_date cannot be after end_date")

    query = text("""
        SELECT
            t.timesheet_id,
            e.employee_code,
            e.full_name,
            t.work_date,
            t.hours_worked,
            t.description,
            t.submission_status,
            t.submitted_at,
            t.approved_at
        FROM public.timesheets AS t
        JOIN public.employees AS e
            ON e.employee_id = t.employee_id
        WHERE t.employee_id = :employee_id
          AND t.work_date BETWEEN :start_date AND :end_date
        ORDER BY t.work_date
    """)

    with engine.connect() as connection:
        rows = connection.execute(
            query,
            {
                "employee_id": employee_id,
                "start_date": start_date,
                "end_date": end_date,
            },
        ).mappings().all()

    return [dict(row) for row in rows]
