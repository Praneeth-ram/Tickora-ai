import getpass

from sqlalchemy import text

from backend.db import engine
from backend.services.auth_service import hash_password

TARGET_CODES = ["EMP001", "EMP002"]


def main():
    with engine.begin() as connection:
        for code in TARGET_CODES:
            employee = connection.execute(
                text("""
                    SELECT id, full_name
                    FROM public.employees
                    WHERE employee_code = :code AND is_active = TRUE
                """),
                {"code": code},
            ).mappings().one_or_none()

            if employee is None:
                print(f"{code}: not found or inactive. Skipping.")
                continue

            print(f"\nEmployee: {employee['full_name']} ({code})")
            password = getpass.getpass("Set password: ")
            confirmation = getpass.getpass("Confirm password: ")

            if password != confirmation:
                print("Passwords do not match. Skipping.")
                continue
            if len(password) < 12:
                print("Use at least 12 characters. Skipping.")
                continue

            digest = hash_password(password)
            params = {"employee_id": employee["id"], "password_hash": digest}

            updated = connection.execute(
                text("""
                    UPDATE public.employee_credentials
                    SET password_hash = :password_hash, is_enabled = TRUE
                    WHERE employee_id = :employee_id
                """),
                params,
            ).rowcount

            if updated == 0:
                connection.execute(
                    text("""
                        INSERT INTO public.employee_credentials
                            (employee_id, password_hash, is_enabled)
                        VALUES (:employee_id, :password_hash, TRUE)
                    """),
                    params,
                )

            print(f"Password configured for {code}.")

    print("\nDone.")


if __name__ == "__main__":
    main()