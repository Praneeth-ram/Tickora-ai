from datetime import date
from sqlalchemy import text
from backend.db import engine
from backend.repositories.timesheet_repository import get_timesheets
from backend.repositories.leave_repository import get_leave_requests
from backend.repositories.wfh_repository import get_wfh_requests
from backend.repositories.calendar_repository import (
    get_holidays,
    get_work_schedules,
)

def main():
    with engine.connect() as connection:
        employee_id = connection.execute(
            text("""
                SELECT id AS employee_id
                FROM public.employees
                WHERE employee_code = :code
            """),
            {"code": "EMP001"},
        ).scalar_one()

    start = date(2026, 10, 1)
    end = date(2026, 10, 31)

    results = {
        "Timesheets": get_timesheets(employee_id, start, end),
        "Leave requests": get_leave_requests(employee_id),
        "WFH requests": get_wfh_requests(employee_id),
        "October holidays": get_holidays(start, end),
        "Work schedule": get_work_schedules(employee_id, end),
    }
    for name, records in results.items():
        print(f"\n{name}: {len(records)} record(s)")
        for record in records:
            print(record)

if __name__ == "__main__":
    main()
