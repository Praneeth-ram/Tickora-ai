"""Short-term chat memory per employee session.

Uses public.chat_sessions. The structured context is stored in last_plan,
which already exists in the database and allows NULL, so no schema change is needed.
"""
import json

from sqlalchemy import text

SESSION_IDLE_MINUTES = 240
MAX_SESSION_ID_LENGTH = 100
MAX_TOPIC_LENGTH = 40


def load_last_topic(engine, employee_id: int, session_id: str) -> str | None:
    if not session_id or len(session_id) > MAX_SESSION_ID_LENGTH:
        return None
    with engine.connect() as connection:
        return connection.execute(
            text("""
                SELECT last_topic FROM public.chat_sessions
                WHERE employee_id = :employee_id
                  AND session_id = :session_id
                  AND last_active > now() - make_interval(mins => :minutes)
            """),
            {"employee_id": employee_id, "session_id": session_id,
             "minutes": SESSION_IDLE_MINUTES},
        ).scalar_one_or_none()


def save_last_topic(engine, employee_id: int, session_id: str, topic: str) -> None:
    if not session_id or len(session_id) > MAX_SESSION_ID_LENGTH:
        return
    with engine.begin() as connection:
        connection.execute(
            text("""
                INSERT INTO public.chat_sessions (employee_id, session_id, last_topic, last_active)
                VALUES (:employee_id, :session_id, :topic, now())
                ON CONFLICT (employee_id, session_id)
                DO UPDATE SET last_topic = EXCLUDED.last_topic, last_active = now()
            """),
            {"employee_id": employee_id, "session_id": session_id,
             "topic": topic[:MAX_TOPIC_LENGTH]},
        )


def save_last_context(engine, employee_id: int, session_id: str,
                      operation_id: str, start_date: str | None, end_date: str | None,
                      fields: list[str] | None = None,
                      subject_id: int | None = None) -> None:
    """Save the operation, its period, requested fields, and subject_id for follow-ups."""
    if not session_id or len(session_id) > MAX_SESSION_ID_LENGTH:
        return
    plan = json.dumps({
        "operation_id": operation_id,
        "start_date": start_date,
        "end_date": end_date,
        "fields": list(fields or []),
        "subject_id": subject_id,
    }, default=str)
    with engine.begin() as connection:
        connection.execute(
            text("""
                INSERT INTO public.chat_sessions
                    (employee_id, session_id, last_topic, last_plan, last_active)
                VALUES (:employee_id, :session_id, :topic, CAST(:plan AS jsonb), now())
                ON CONFLICT (employee_id, session_id)
                DO UPDATE SET last_topic = EXCLUDED.last_topic,
                              last_plan = EXCLUDED.last_plan,
                              last_active = now()
            """),
            {"employee_id": employee_id, "session_id": session_id,
             "topic": operation_id[:MAX_TOPIC_LENGTH], "plan": plan},
        )

def load_last_context(engine, employee_id: int, session_id: str) -> dict | None:
    if not session_id or len(session_id) > MAX_SESSION_ID_LENGTH:
        return None
    with engine.connect() as connection:
        value = connection.execute(
            text("""
                SELECT last_plan FROM public.chat_sessions
                WHERE employee_id = :employee_id
                  AND session_id = :session_id
                  AND last_active > now() - make_interval(mins => :minutes)
            """),
            {"employee_id": employee_id, "session_id": session_id,
             "minutes": SESSION_IDLE_MINUTES},
        ).scalar_one_or_none()
    return value if isinstance(value, dict) else None


def purge_expired(engine) -> int:
    with engine.begin() as connection:
        result = connection.execute(
            text("""
                DELETE FROM public.chat_sessions
                WHERE last_active < now() - make_interval(mins => :minutes)
            """),
            {"minutes": SESSION_IDLE_MINUTES},
        )
        return result.rowcount