from datetime import date
from sqlalchemy import text
from backend.db import engine

def get_holidays(
    start_date: date,
    end_date: date,
    region: str | None = None,
) -> list[dict]:
    # Retrieve active holidays within a date range.

    if start_date > end_date:
        raise ValueError("start_date cannot be after end_date")

    query = text("""
        SELECT
            holiday_id,
            holiday_date,
            holiday_name,
            region
        FROM public.holidays
        WHERE is_active = TRUE
          AND holiday_date BETWEEN :start_date AND :end_date
          AND (
              CAST(:region AS VARCHAR) IS NULL
              OR region = CAST(:region AS VARCHAR)
          )
        ORDER BY holiday_date
    """)

    with engine.connect() as connection:
        rows = connection.execute(
            query,
            {
                "start_date": start_date,
                "end_date": end_date,
                "region": region,
            },
        ).mappings().all()

    return [dict(row) for row in rows]


def get_work_schedules(
    employee_id: int,
    on_date: date,
) -> list[dict]:
    """Retrieve schedules effective on a particular date."""

    query = text("""
        SELECT
            schedule_id,
            employee_id,
            effective_from,
            effective_to,
            shift_start,
            shift_end,
            workdays,
            expected_hours
        FROM public.work_schedules
        WHERE employee_id = :employee_id
          AND effective_from <= :on_date
          AND (
              effective_to IS NULL
              OR effective_to >= :on_date
          )
        ORDER BY effective_from DESC
    """)

    with engine.connect() as connection:
        rows = connection.execute(
            query,
            {
                "employee_id": employee_id,
                "on_date": on_date,
            },
        ).mappings().all()

    return [dict(row) for row in rows]
