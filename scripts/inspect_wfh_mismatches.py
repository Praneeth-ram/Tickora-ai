import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.db import engine
from sqlalchemy import text

query = text("""
    SELECT
        e.employee_code,
        a.attendance_date,
        a.status AS attendance_status,
        a.clock_in,
        a.clock_out,
        a.worked_minutes,
        a.is_late,
        a.work_location,
        w.id AS wfh_request_id,
        w.start_date,
        w.end_date,
        w.status AS wfh_status
    FROM attendance_records a
    JOIN employees e ON e.id = a.employee_id
    JOIN wfh_requests w
      ON w.employee_id = a.employee_id
     AND a.attendance_date BETWEEN w.start_date AND w.end_date
    WHERE w.status = 'approved'
      AND a.status <> 'work_from_home'
    ORDER BY a.attendance_date, e.employee_code
""")

with engine.connect() as conn:
    rows = conn.execute(query).mappings().all()

    for row in rows:
        print("-" * 70)
        for key, value in row.items():
            print(f"{key}: {value}")
