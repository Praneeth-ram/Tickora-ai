# backend/tests/conftest.py
"""Shared fixtures for integration tests that hit the real dev database.
These tests require a running Postgres with the seeded dev data described
in the project status doc (EMP001 super_admin/org1/dept1, EMP002 admin/org1/dept2,
EMP011, EMP012 employees/org1/dept2, EMP003 employee/org1/dept3).
"""
import pytest
from backend.security.access_policy import Actor, set_actor, reset_actor

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