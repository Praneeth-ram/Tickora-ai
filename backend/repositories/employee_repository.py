from sqlalchemy import text
from backend.db import engine

def get_active_employee_organization(employee_id: int, employee_code: str) -> int | None:
    with engine.connect() as connection:
        return connection.execute(
            text("""
                SELECT organization_id
                FROM public.employees
                WHERE id = :employee_id
                  AND employee_code = :employee_code
                  AND is_active = TRUE
            """),
            {"employee_id": employee_id, "employee_code": employee_code},
        ).scalar_one_or_none()