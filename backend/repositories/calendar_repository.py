from datetime import date

from sqlalchemy import text

from backend.db import engine


def get_holidays(
    start_date: date,
    end_date: date,
    region: str | None = None,
    organization_id: int | None = None,
) -> list[dict]:
    """Retrieve holidays from calendars matching the supplied filters."""

    if start_date > end_date:
        raise ValueError("start_date cannot be after end_date")

    query = text("""
        SELECT
            h.id AS holiday_id,
            h.holiday_date,
            h.name AS holiday_name,
            hc.region,
            hc.name AS calendar_name
        FROM public.holidays AS h
        JOIN public.holiday_calendars AS hc
            ON hc.id = h.calendar_id
        JOIN public.organizations AS o
            ON o.id = hc.organization_id
        WHERE h.holiday_date BETWEEN :start_date AND :end_date
          AND o.is_active = TRUE
          AND (
              CAST(:region AS VARCHAR) IS NULL
              OR hc.region = CAST(:region AS VARCHAR)
          )
          AND (
              CAST(:organization_id AS BIGINT) IS NULL
              OR hc.organization_id = CAST(:organization_id AS BIGINT)
          )
        ORDER BY h.holiday_date
    """)

    with engine.connect() as connection:
        rows = connection.execute(
            query,
            {
                "start_date": start_date,
                "end_date": end_date,
                "region": region,
                "organization_id": organization_id,
            },
        ).mappings().all()

    return [dict(row) for row in rows]


def get_work_schedules(
    employee_id: int,
    on_date: date,
) -> list[dict]:
    """Retrieve the employee's assigned schedule and applicable day details."""

    query = text("""
        SELECT
            ws.id AS schedule_id,
            esa.employee_id,
            esa.effective_from,
            esa.effective_to,
            ws.name AS schedule_name,
            ws.schedule_type,
            sd.day_of_week,
            sd.start_time AS shift_start,
            sd.end_time AS shift_end,
            sd.break_minutes,
            sd.required_minutes,
            sd.is_working_day
        FROM public.employee_schedule_assignments AS esa
        JOIN public.work_schedules AS ws
            ON ws.id = esa.schedule_id
        LEFT JOIN public.schedule_days AS sd
            ON sd.schedule_id = ws.id
           AND sd.day_of_week = EXTRACT(
               DOW FROM CAST(:on_date AS DATE)
           )::INTEGER
        WHERE esa.employee_id = :employee_id
          AND esa.effective_from <= :on_date
          AND (
              esa.effective_to IS NULL
              OR esa.effective_to >= :on_date
          )
          AND ws.is_active = TRUE
        ORDER BY esa.effective_from DESC
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