"""allow null reason in chat feedback
Revision ID: 005a84e708b2
Revises: ddad5b2f3fb6
Create Date: 2026-11-14 11:30:29.120029

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '005a84e708b2'
down_revision: Union[str, None] = 'ddad5b2f3fb6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.execute("ALTER TABLE public.chat_feedback ALTER COLUMN reason DROP NOT NULL")
    op.execute("ALTER TABLE public.chat_feedback DROP CONSTRAINT IF EXISTS chat_feedback_reason_check")
    op.execute("""
ALTER TABLE public.chat_feedback ADD CONSTRAINT chat_feedback_reason_check CHECK (
    reason IS NULL OR reason IN ('wrong_number', 'wrong_period', 'wrong_intent', 'unhelpful', 'other')
)
""")

def downgrade() -> None:
    op.execute("DELETE FROM public.chat_feedback WHERE reason IS NULL")
    op.execute("ALTER TABLE public.chat_feedback ALTER COLUMN reason SET NOT NULL")
