import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import inspect
from backend.db import engine

inspector = inspect(engine)

for table_name in [
    "organizations",
    "employees",
    "attendance_records",
    "timesheets",
    "timesheet_entries",
    "holidays",
]:
    print(f"\n--- {table_name} ---")

    if not inspector.has_table(table_name, schema="public"):
        print("TABLE NOT FOUND")
        continue

    for column in inspector.get_columns(table_name, schema="public"):
        print(f"{column['name']}: {column['type']}")

    pk = inspector.get_pk_constraint(table_name, schema="public")
    print("Primary key:", pk.get("constrained_columns"))

    fks = inspector.get_foreign_keys(table_name, schema="public")
    for fk in fks:
        print(
            "Foreign key:",
            fk.get("constrained_columns"),
            "->",
            fk.get("referred_table"),
            fk.get("referred_columns"),
        )
