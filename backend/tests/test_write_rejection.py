# backend/tests/test_write_rejection.py
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from backend.tests.conftest import requires_agent_role
from backend.db import agent_engine

pytestmark = requires_agent_role


@pytest.mark.parametrize("sql", [
    "INSERT INTO public.attendance_records (employee_id, attendance_date, status) "
    "VALUES (11, '2026-11-01', 'PRESENT')",
    "UPDATE public.attendance_records SET status = 'ABSENT' WHERE employee_id = 11",
    "DELETE FROM public.attendance_records WHERE employee_id = 11",
])
def test_agent_role_cannot_write(sql):
    with pytest.raises(DBAPIError) as exc_info:
        with agent_engine.connect() as conn:
            conn.execute(text(sql))
            conn.commit()
    error_message = str(exc_info.value).lower()
    assert (
        "permission denied" in error_message
        or "read-only transaction" in error_message
    )


def test_agent_role_cannot_escalate_via_set_role():
    with pytest.raises(DBAPIError):
        with agent_engine.connect() as conn:
            conn.execute(text("SET ROLE postgres"))