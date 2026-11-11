# backend/tests/test_enumeration_integration.py
# import pytest

from backend.tests.conftest import requires_db
from backend.db import engine
from backend.security.access_policy import load_actor
from backend.security.subject_resolution import resolve_subject, names_a_person

pytestmark = requires_db


def test_unknown_and_out_of_scope_named_subjects_resolve_identically(as_actor):
    from backend.tests.conftest import EMP002

    with engine.connect() as connection:
        actor = load_actor(connection, EMP002[0], "EMP002")

        # Arjun Kumar (EMP003) is a real person, but in a department EMP002 can't see.
        out_of_scope = resolve_subject(connection, actor, "Show Arjun Kumar's attendance for October.")
        # No such person exists anywhere.
        unknown = resolve_subject(connection, actor, "Show Priyanka Deshmukh's attendance for October.")

    assert out_of_scope is None
    assert unknown is None
    # Both fall through to the same names_a_person() gate in main.py and
    # therefore both produce NOT_FOUND_MESSAGE, never a different message
    # that would hint one of them exists.
    assert names_a_person("Show Arjun Kumar's attendance for October.", actor)
    assert names_a_person("Show Priyanka Deshmukh's attendance for October.", actor)