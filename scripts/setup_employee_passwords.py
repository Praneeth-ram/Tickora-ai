import getpass
from sqlalchemy import text
from backend.db import engine
from backend.services.auth_service import hash_password

def main():
    with engine.begin() as connection:
        employees = connection.execute(
            text("""
                SELECT employee_id, employee_code, full_name
                FROM public.employees
                WHERE is_active = TRUE
                ORDER BY employee_code
            """)
        ).mappings().all()

        if not employees:
            print("No active employees found.")
            return

        for employee in employees:
            code = employee["employee_code"]
            name = employee["full_name"]

            print(f"\nEmployee: {name} ({code})")

            password = getpass.getpass("Set password: ")
            confirmation = getpass.getpass("Confirm password: ")

            if password != confirmation:
                print("Passwords do not match. Skipping this employee.")
                continue

            if len(password) < 12:
                print("Use at least 12 characters. Skipping this employee.")
                continue

            password_digest = hash_password(password)

            connection.execute(
                text("""
                    INSERT INTO public.employee_credentials
                        (employee_id, password_hash, is_enabled)
                    VALUES
                        (:employee_id, :password_hash, TRUE)
                    ON CONFLICT (employee_id)
                    DO UPDATE SET
                        password_hash = EXCLUDED.password_hash,
                        is_enabled = TRUE,
                        updated_at = NOW()
                """),
                {
                    "employee_id": employee["employee_id"],
                    "password_hash": password_digest,
                },
            )

            print(f"Password configured for {code}.")

    print("\nPassword setup finished.")

if __name__ == "__main__":
    main()
