from logging.config import fileConfig
from alembic import context
from sqlalchemy import pool
from backend.db import Base, engine

config = context.config

# The application's database URL is loaded from .env by backend.db.
# Do not print or store credentials in migration files.
target_metadata = Base.metadata

def run_migrations_offline() -> None:
    """Generate SQL without opening a database connection."""
    from backend.db import DATABASE_URL

    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Run migrations using the application's SQLAlchemy engine."""
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
