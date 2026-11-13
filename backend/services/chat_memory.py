from sqlalchemy import text

SESSION_IDLE_MINUTES = 30
MAX_SESSION_ID_LENGTH = 100

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
            {"employee_id": employee_id, "session_id": session_id, "topic": topic[:40]},
        )

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