import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.db import engine
from sqlalchemy import text

queries = {
    "Departments": "SELECT COUNT(*) FROM departments",
    "Teams": "SELECT COUNT(*) FROM teams",
    "Employees": "SELECT COUNT(*) FROM employees",
    "Schedules": "SELECT COUNT(*) FROM work_schedules",
    "Holidays": "SELECT COUNT(*) FROM holidays",
    "Attendance": "SELECT COUNT(*) FROM attendance_records",
    "Attendance status breakdown": """
        SELECT status, COUNT(*)
        FROM attendance_records
        GROUP BY status
        ORDER BY status
    """,
    "Leave requests": "SELECT COUNT(*) FROM leave_requests",
    "WFH requests": "SELECT COUNT(*) FROM wfh_requests",
    "Timesheets": "SELECT COUNT(*) FROM timesheets",
    "Timesheet entries": "SELECT COUNT(*) FROM timesheet_entries",
    "Payroll periods": "SELECT COUNT(*) FROM payroll_periods",
}

with engine.connect() as conn:
    print("DATABASE:", engine.url.database)

    for label, query in queries.items():
        print(f"\n--- {label} ---")
        result = conn.execute(text(query))

        if label == "Attendance status breakdown":
            for row in result:
                print(f"{row[0]}: {row[1]}")
        else:
            print(result.scalar_one())