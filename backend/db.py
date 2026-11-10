# backend/db.py
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase
from backend.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_recycle=settings.db_pool_recycle_seconds,
    pool_pre_ping=True,
)

agent_url = settings.agent_database_url
if not agent_url:
    raise RuntimeError(
        "AGENT_DATABASE_URL is not set. The chatbot must not run on the owner account."
    )

agent_engine = create_engine(agent_url, pool_pre_ping=True)

class Base(DeclarativeBase):
    pass

def test_connection() -> str:
    with engine.connect() as connection:
        return connection.execute(text("SELECT current_database()")).scalar_one()