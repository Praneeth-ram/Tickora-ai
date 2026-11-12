# backend/tests/conftest.py
"""Shared fixtures for integration tests that hit the real dev database.
These tests require a running Postgres with the seeded dev data described
in the project status doc (EMP001 super_admin/org1/dept1, EMP002 admin/org1/dept2,
EMP011, EMP012 employees/org1/dept2, EMP003 employee/org1/dept3).
"""
from sqlalchemy import create_engine, text

import pytest
from backend.security.access_policy import Actor, set_actor, reset_actor
from backend.config import get_settings

# (employee_id, organization_id, department_id, role)
EMP001 = (1, 1, 1, "super_admin")
EMP002 = (2, 1, 2, "admin")
EMP011 = (11, 1, 2, "employee")
EMP012 = (12, 1, 2, "employee")
EMP003 = (3, 1, 3, "employee")


@pytest.fixture
def as_actor():
    """as_actor(*EMP002) sets the context actor for the duration of the test."""
    tokens = []

    def _set(employee_id, organization_id, department_id, role):
        actor = Actor(employee_id, organization_id, department_id, role)
        tokens.append(set_actor(actor))
        return actor

    yield _set

    for token in reversed(tokens):
        reset_actor(token)

def _db_ready() -> bool:
    try:
        engine = create_engine(get_settings().database_url, connect_args={"connect_timeout": 3})
        engine.connect().close()
        return True
    except Exception:
        return False

def _agent_role_ready() -> bool:
    url = get_settings().agent_database_url
    if not url:
        return False
    try:
        engine = create_engine(url, connect_args={"connect_timeout": 3})
        with engine.connect() as c:
            return c.execute(text("select current_user")).scalar() == "tickora_agent"
    except Exception:
        return False


requires_db = pytest.mark.skipif(not _db_ready(), reason="needs PostgreSQL")
requires_agent_role = pytest.mark.skipif(
    not _agent_role_ready(), reason="needs tickora_agent login"
)
