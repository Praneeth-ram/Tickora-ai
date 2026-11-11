
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.db import engine
from sqlalchemy import text

checks = {
    "Duplicate employee attendance dates": """
        SELECT COUNT(*) FROM (
            SELECT employee_id, attendance_date
            FROM attendance_records
            GROUP BY employee_id, attendance_date
            HAVING COUNT(*) > 1
        ) duplicates
    """,
    "Attendance dates in the future": """
        SELECT COUNT(*) FROM attendance_records
        WHERE attendance_date > CURRENT_DATE
    """,
    "Clock-out before clock-in": """
        SELECT COUNT(*) FROM attendance_records
        WHERE clock_in IS NOT NULL
          AND clock_out IS NOT NULL
          AND clock_out < clock_in
    """,
    "Approved leave overlapping attendance": """
        SELECT COUNT(*)
        FROM attendance_records a
        JOIN leave_requests l
          ON l.employee_id = a.employee_id
         AND a.attendance_date BETWEEN l.start_date AND l.end_date
        WHERE l.status = 'approved'
          AND a.status IN ('present', 'late', 'half_day', 'work_from_home')
    """,
    "Worked attendance during approved WFH with non-remote location": """
        SELECT COUNT(*)
        FROM attendance_records a
        JOIN wfh_requests w
          ON w.employee_id = a.employee_id
         AND a.attendance_date BETWEEN w.start_date AND w.end_date
        WHERE w.status = 'approved'
          AND a.clock_in IS NOT NULL
          AND a.status IN ('present', 'late', 'half_day', 'work_from_home')
          AND (
              a.work_location IS NULL
              OR LOWER(a.work_location) <> 'remote'
          )
    """,
    "Attendance punches without parent record": """
        SELECT COUNT(*)
        FROM attendance_punches p
        LEFT JOIN attendance_records a ON a.id = p.attendance_id
        WHERE a.id IS NULL
    """,
    "Timesheet entries without parent timesheet": """
        SELECT COUNT(*)
        FROM timesheet_entries e
        LEFT JOIN timesheets t ON t.id = e.timesheet_id
        WHERE t.id IS NULL
    """,
    "Negative worked minutes": """
        SELECT COUNT(*) FROM attendance_records
        WHERE worked_minutes < 0 OR overtime_minutes < 0
    """,
}

with engine.connect() as conn:
    print("Database:", engine.url.database)

    for label, query in checks.items():
        count = conn.execute(text(query)).scalar_one()
        print(f"{label}: {count}")
