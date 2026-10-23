from datetime import date
from sqlalchemy import text
from backend.db import engine

def get_attendance_records(
    employee_id: int,
    start_date: date,
    end_date: date,
) -> list[dict]:
    """Return attendance records for one employee within a date range."""

    if start_date > end_date:
        raise ValueError("start_date cannot be after end_date")

    query = text("""
        SELECT
            a.id AS attendance_id,
            e.employee_code,
            e.full_name,
            a.attendance_date,
            a.clock_in,
            a.clock_out,
            a.status,
            a.work_location,
            a.worked_minutes,
            a.overtime_minutes,
            a.is_late
        FROM public.attendance_records AS a
        JOIN public.employees AS e
            ON e.id = a.employee_id
        WHERE a.employee_id = :employee_id
          AND a.attendance_date BETWEEN :start_date AND :end_date
        ORDER BY a.attendance_date ASC
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
    """Return attendance totals for one employee within a date range."""

    if start_date > end_date:
        raise ValueError("start_date cannot be after end_date")

    query = text("""
        SELECT
            COUNT(*) AS recorded_days,

            COUNT(*) FILTER (
                WHERE status IN ('present', 'late', 'half_day')
            ) AS attended_days,

            COUNT(*) FILTER (
                WHERE status = 'absent'
            ) AS absent_days,

            COUNT(*) FILTER (
                WHERE status = 'late'
            ) AS late_days,

            COUNT(*) FILTER (
                WHERE status = 'half_day'
            ) AS half_days,

            COUNT(*) FILTER (
                WHERE status = 'on_leave'
            ) AS leave_days,

            COUNT(*) FILTER (
                WHERE work_location = 'remote'
            ) AS remote_days,

            COALESCE(SUM(worked_minutes), 0) AS total_worked_minutes,

            COALESCE(SUM(overtime_minutes), 0) AS total_overtime_minutes

        FROM public.attendance_records
        WHERE employee_id = :employee_id
          AND attendance_date BETWEEN :start_date AND :end_date
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
