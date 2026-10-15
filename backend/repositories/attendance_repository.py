from datetime import date
from sqlalchemy import text
from backend.db import engine

def get_attendance_records(
    employee_id: int,
    start_date: date,
    end_date: date,
) -> list[dict]:
    # Return attendance records for one employee within a date range.

    if start_date > end_date:
        raise ValueError("start_date cannot be after end_date")

    query = text("""
        SELECT
            a.attendance_id,
            e.employee_code,
            e.full_name,
            a.work_date,
            a.clock_in,
            a.clock_out,
            a.status,
            a.work_location
        FROM public.attendance_records AS a
        JOIN public.employees AS e
            ON e.employee_id = a.employee_id
        WHERE a.employee_id = :employee_id
          AND a.work_date BETWEEN :start_date AND :end_date
        ORDER BY a.work_date ASC
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


def get_attendance_summary(
    employee_id: int,
    start_date: date,
    end_date: date,
) -> dict:
    """Return attendance totals grouped by status."""

    if start_date > end_date:
        raise ValueError("start_date cannot be after end_date")

    query = text("""
        SELECT
            COUNT(*) AS recorded_days,
            COUNT(*) FILTER (
                WHERE status IN ('PRESENT', 'LATE')
            ) AS present_days,
            COUNT(*) FILTER (
                WHERE status = 'ABSENT'
            ) AS absent_days,
            COUNT(*) FILTER (
                WHERE status = 'LATE'
            ) AS late_days,
            COUNT(*) FILTER (
                WHERE status = 'HALF_DAY'
            ) AS half_days,
            COUNT(*) FILTER (
                WHERE status = 'ON_LEAVE'
            ) AS leave_days,
            COUNT(*) FILTER (
                WHERE work_location = 'WFH'
            ) AS wfh_days
        FROM public.attendance_records
        WHERE employee_id = :employee_id
          AND work_date BETWEEN :start_date AND :end_date
    """)

    with engine.connect() as connection:
        row = connection.execute(
            query,
            {
                "employee_id": employee_id,
                "start_date": start_date,
                "end_date": end_date,
            },
        ).mappings().one()

    return dict(row)
