"""Short-term chat memory per employee session."""
from alembic import op

revision = "20261107_chat_sessions"
down_revision = "20261106_rls_policies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE public.chat_sessions (
            employee_id bigint NOT NULL REFERENCES public.employees(id) ON DELETE CASCADE,
            session_id varchar(100) NOT NULL,
            last_topic varchar(40),
            last_active timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (employee_id, session_id)
        )
    """)
    op.execute("CREATE INDEX ix_chat_sessions_last_active ON public.chat_sessions (last_active)")
    # The chatbot's read role must never see this table; the app reads it with the owner connection.
    op.execute("REVOKE ALL ON public.chat_sessions FROM tickora_agent")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.chat_sessions")