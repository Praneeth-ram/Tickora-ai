from datetime import date
from sqlalchemy import text
from backend.db import engine

def get_leave_requests(
    employee_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
    status: str | None = None,
) -> list[dict]:
    # Retrieve leave requests, optionally filtered by dates and status.

    if start_date and end_date and start_date > end_date:
        raise ValueError("start_date cannot be after end_date")

    if status is not None:
        status = status.upper()
        if status not in {"PENDING", "APPROVED", "REJECTED", "CANCELLED"}:
            raise ValueError("Invalid leave-request status")

    query = text("""
        SELECT
            l.leave_request_id,
            e.employee_code,
            e.full_name,
            l.leave_type,
            l.start_date,
            l.end_date,
            l.reason,
            l.status,
            l.requested_at,
            l.reviewed_at
        FROM public.leave_requests AS l
        JOIN public.employees AS e
            ON e.employee_id = l.employee_id
        WHERE l.employee_id = :employee_id
          AND (
              CAST(:start_date AS DATE) IS NULL
              OR l.end_date >= CAST(:start_date AS DATE)
          )
          AND (
              CAST(:end_date AS DATE) IS NULL
              OR l.start_date <= CAST(:end_date AS DATE)
          )
          AND (
              CAST(:status AS VARCHAR) IS NULL
              OR l.status = CAST(:status AS VARCHAR)
          )
        ORDER BY l.start_date
    """)

    with engine.connect() as connection:
        rows = connection.execute(
            query,
            {
                "employee_id": employee_id,
                "start_date": start_date,
                "end_date": end_date,
                "status": status,
            },
        ).mappings().all()

    return [dict(row) for row in rows]
