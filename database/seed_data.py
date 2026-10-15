from sqlalchemy import text
from backend.db import engine

TABLES = (
    "departments",
    "employees",
    "work_schedules",
    "holidays",
    "attendance_records",
    "timesheets",
    "leave_requests",
    "wfh_requests",
)

def validate_seed_data() -> None:
   with engine.connect() as connection:
        print("\nTickora database validation")
        print("-" * 40)

        total_records = 0

        for table in TABLES:
            query = text(f"SELECT COUNT(*) FROM public.{table}")
            count = connection.execute(query).scalar_one()

            print(f"{table:<22} {count:>5} records")
            total_records += count

        print("-" * 40)
        print(f"{'Total records':<22} {total_records:>5}")

        if total_records == 0:
            raise RuntimeError("No sample data found in the database.")

        empty_tables = []

        for table in TABLES:
            count = connection.execute(
                text(f"SELECT COUNT(*) FROM public.{table}")
            ).scalar_one()

            if count == 0:
                empty_tables.append(table)

        if empty_tables:
            print("\nWARNING: These tables are empty:")
            for table in empty_tables:
                print(f"- {table}")
        else:
            print("\nSUCCESS: All eight tables contain data.")


if __name__ == "__main__":
    validate_seed_data()
