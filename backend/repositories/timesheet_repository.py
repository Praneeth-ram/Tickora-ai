from datetime import date
from sqlalchemy import text
from backend.db import engine

def get_timesheets(
    employee_id: int,
    start_date: date,
    end_date: date,
) -> list[dict]:
    """Retrieve an employee's timesheets overlapping a date range."""

    if start_date > end_date:
        raise ValueError("start_date cannot be after end_date")

    query = text("""
        SELECT
            t.id AS timesheet_id,
            e.employee_code,
            e.full_name,
            t.period_start,
            t.period_end,
            t.status,
            t.submitted_at,
            t.approved_at,
            COALESCE(SUM(te.worked_minutes), 0)
                AS total_worked_minutes
        FROM public.timesheets AS t
        JOIN public.employees AS e
            ON e.id = t.employee_id
        LEFT JOIN public.timesheet_entries AS te
            ON te.timesheet_id = t.id
           AND te.work_date BETWEEN :start_date AND :end_date
        WHERE t.employee_id = :employee_id
          AND t.period_start <= :end_date
          AND t.period_end >= :start_date
        GROUP BY
            t.id,
            e.employee_code,
            e.full_name,
            t.period_start,
            t.period_end,
            t.status,
            t.submitted_at,
            t.approved_at
        ORDER BY t.period_start
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