from datetime import date
from backend.repositories.attendance_repository import (
    get_attendance_records,
    get_attendance_summary,
)

def main():
    # EMP001 is the sample employee Arun Kumar.
    # Resolve the database ID instead of assuming it equals 1.
    from sqlalchemy import text
    from backend.db import engine

    with engine.connect() as connection:
        employee_id = connection.execute(
            text("""
                SELECT employee_id
                FROM public.employees
                WHERE employee_code = :employee_code
            """),
            {"employee_code": "EMP001"},
        ).scalar_one()

    start_date = date(2026, 10, 1)
    end_date = date(2026, 10, 31)

    records = get_attendance_records(
        employee_id, start_date, end_date
    )
    summary = get_attendance_summary(
        employee_id, start_date, end_date
    )

    print("\nAttendance records")
    for record in records:
        print(record)

    print("\nAttendance summary")
    for key, value in summary.items():
        print(f"{key}: {value}")

if __name__ == "__main__":
    main()
