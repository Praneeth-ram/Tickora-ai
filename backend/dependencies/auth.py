from typing import Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from backend.db import engine
from backend.services.auth_service import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)

def get_current_employee(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> dict:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(credentials.credentials)
        employee_id = int(payload["sub"])
    except (ValueError, KeyError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    query = text("""
    SELECT
        id AS employee_id,
        organization_id,
        employee_code,
        full_name,
        email
    FROM public.employees
    WHERE id = :employee_id
      AND is_active = TRUE
    """)

    with engine.connect() as connection:
        employee = connection.execute(
            query, {"employee_id": employee_id}
        ).mappings().one_or_none()

    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Employee is inactive or does not exist",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return dict(employee)
