from typing import Sequence, Union
from alembic import op

revision: str = "ddad5b2f3fb6"
down_revision: Union[str, None] = "20261107_chat_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.execute("""
CREATE TABLE IF NOT EXISTS public.chat_feedback (
    id BIGSERIAL PRIMARY KEY,
    request_id TEXT NOT NULL,
    employee_id INTEGER NOT NULL REFERENCES public.employees(id),
    rating TEXT NOT NULL CHECK (rating IN ('up', 'down')),
    reason TEXT NOT NULL CHECK (reason IN (
        'wrong_number', 'wrong_period', 'wrong_intent', 'unhelpful', 'other'
    )),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS chat_feedback_employee_idx
    ON public.chat_feedback (employee_id);
CREATE INDEX IF NOT EXISTS chat_feedback_created_idx
    ON public.chat_feedback (created_at);
""")

    op.execute("""
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tickora_agent') THEN
        REVOKE ALL ON public.chat_feedback FROM tickora_agent;
    END IF;
END $$;
""")

def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.chat_feedback")