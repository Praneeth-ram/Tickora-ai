"""add employee credentials

Revision ID: 2454655f091b
Revises: 02db87cd6f48
Create Date: 2026-10-24 16:46:53.386702

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2454655f091b'
down_revision: Union[str, None] = '02db87cd6f48'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "employee_credentials",
        sa.Column(
            "employee_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "employees.id",
                ondelete="CASCADE",
            ),
            primary_key=True,
        ),
        sa.Column(
            "password_hash",
            sa.String(255),
            nullable=False,
        ),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

def downgrade() -> None:
    op.drop_table("employee_credentials")