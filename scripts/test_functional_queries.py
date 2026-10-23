import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.db import engine
from sqlalchemy import text

tests = {
    "Employee lookup": """
        SELECT employee_code, full_name, email
        FROM employees
        WHERE employee_code = :employee_code
          AND is_active = TRUE
    """,
    "Monthly attendance summary": """
        SELECT
            COUNT(*) AS total_records,
            COUNT(*) FILTER (
                WHERE status IN ('present', 'late', 'half_day', 'work_from_home')
            ) AS attended_days,
            COUNT(*) FILTER (WHERE status = 'absent') AS absent_days,
            COUNT(*) FILTER (WHERE status = 'late') AS late_days,
            COALESCE(SUM(worked_minutes), 0) AS total_worked_minutes
        FROM attendance_records a
        JOIN employees e ON e.id = a.employee_id
        WHERE e.employee_code = :employee_code
          AND a.attendance_date BETWEEN :start_date AND :end_date
    """,
    "Leave request summary": """
        SELECT
            status,
            COUNT(*) AS request_count
        FROM leave_requests l
        JOIN employees e ON e.id = l.employee_id
        WHERE e.employee_code = :employee_code
        GROUP BY status
        ORDER BY status
    """,
    "WFH request summary": """
        SELECT
            status,
            COUNT(*) AS request_count
        FROM wfh_requests w
        JOIN employees e ON e.id = w.employee_id
        WHERE e.employee_code = :employee_code
        GROUP BY status
        ORDER BY status
    """,
    "Timesheet summary": """
        SELECT
            t.status,
            COUNT(DISTINCT t.id) AS timesheet_count,
            COALESCE(SUM(te.worked_minutes), 0) AS logged_minutes
        FROM timesheets t
        JOIN employees e ON e.id = t.employee_id
        LEFT JOIN timesheet_entries te ON te.timesheet_id = t.id
        WHERE e.employee_code = :employee_code
        GROUP BY t.status
        ORDER BY t.status
    """,
}

params = {
    "employee_code": "EMP001",
    "start_date": "2026-10-01",
    "end_date": "2026-10-23",
}

with engine.connect() as conn:
    print("Database:", engine.url.database)

    for name, query in tests.items():
        print(f"\n--- {name} ---")
        rows = conn.execute(text(query), params).mappings().all()

        if not rows:
            print("No matching records.")
        else:
            for row in rows:
                print(dict(row))
