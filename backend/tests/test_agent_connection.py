import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from backend.tests.conftest import requires_db, requires_agent_role
from backend.db import agent_engine

pytestmark = requires_agent_role

def test_agent_engine_connects_as_read_only_role():
    with agent_engine.connect() as connection:
        user = connection.execute(text("SELECT current_user")).scalar_one()
    assert user == "tickora_agent"

def test_agent_role_cannot_write():
    with agent_engine.connect() as connection:
        with pytest.raises(DBAPIError):
            connection.execute(
                text("UPDATE public.employees SET is_active = is_active WHERE FALSE")
            )