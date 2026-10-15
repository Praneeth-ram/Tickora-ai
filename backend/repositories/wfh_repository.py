from datetime import date
from sqlalchemy import text
from backend.db import engine

def get_wfh_requests(
    employee_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
    status: str | None = None,
) -> list[dict]:
    # Retrieve work-from-home requests.

    if start_date and end_date and start_date > end_date:
        raise ValueError("start_date cannot be after end_date")

    if status is not None:
        status = status.upper()
        if status not in {"PENDING", "APPROVED", "REJECTED", "CANCELLED"}:
            raise ValueError("Invalid WFH-request status")

    query = text("""
        SELECT
            w.wfh_request_id,
            e.employee_code,
            e.full_name,
            w.start_date,
            w.end_date,
            w.reason,
            w.status,
            w.requested_at,
            w.reviewed_at
        FROM public.wfh_requests AS w
        JOIN public.employees AS e
            ON e.employee_id = w.employee_id
        WHERE w.employee_id = :employee_id
          AND (
              CAST(:start_date AS DATE) IS NULL
              OR w.end_date >= CAST(:start_date AS DATE)
          )
          AND (
              CAST(:end_date AS DATE) IS NULL
              OR w.start_date <= CAST(:end_date AS DATE)
          )
          AND (
              CAST(:status AS VARCHAR) IS NULL
              OR w.status = CAST(:status AS VARCHAR)
          )
        ORDER BY w.start_date
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
