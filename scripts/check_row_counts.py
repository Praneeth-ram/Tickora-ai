import sys
from pathlib import Path

# Add the project root to Python's import path.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.db import engine
from sqlalchemy import inspect, text

tables_to_check = [
    "organizations",
    "employees",
    "attendance_records",
    "attendance_punches",
    "leave_requests",
    "wfh_requests",
    "holidays",
    "timesheets",
]

inspector = inspect(engine)
existing_tables = set(inspector.get_table_names())

with engine.connect() as connection:
    for table in tables_to_check:
        if table not in existing_tables:
            print(f"{table}: TABLE NOT FOUND")
            continue

        count = connection.execute(
            text(f'SELECT COUNT(*) FROM "{table}"')
        ).scalar_one()

        print(f"{table}: {count} rows")