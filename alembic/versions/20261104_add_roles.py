"""add role to employees"""
import sqlalchemy as sa
from alembic import op

revision = "20261104_add_roles"
down_revision = "253ab97da22b"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "employees",
        sa.Column("role", sa.String(20), nullable=False, server_default="employee"),
    )
    op.create_check_constraint(
        "ck_employees_role",
        "employees",
        "role IN ('employee', 'admin', 'super_admin')",
    )


def downgrade():
    op.drop_constraint("ck_employees_role", "employees", type_="check")
    op.drop_column("employees", "role")