import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.db import engine
from sqlalchemy import inspect

inspector = inspect(engine)

for table in [
    "organizations",
    "departments",
    "teams",
    "employees",
    "work_schedules",
    "schedule_days",
    "attendance_records",
    "attendance_punches",
    "leave_types",
    "leave_requests",
    "wfh_requests",
    "projects",
    "timesheets",
    "timesheet_entries",
    "payroll_periods",
    "payroll_summaries",
]:
    print(f"\n--- {table} ---")
    for column in inspector.get_columns(table):
        print(
            f"{column['name']}: "
            f"type={column['type']}, "
            f"nullable={column['nullable']}, "
            f"default={column.get('default')}, "
            f"identity={column.get('identity')}"
        )