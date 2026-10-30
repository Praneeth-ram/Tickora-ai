"""create tasks table

Revision ID: 4a6062c34b99
Revises: 2454655f091b
Create Date: 2026-10-29 15:01:25.252870

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4a6062c34b99'
down_revision: Union[str, None] = '2454655f091b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column(
            "id",
            sa.BigInteger,
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "organization_id",
            sa.BigInteger,
            sa.ForeignKey(
                "organizations.id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("project_id", sa.BigInteger, nullable=False),
        sa.Column("task_date", sa.Date, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("start_time", sa.Time, nullable=False),
        sa.Column("end_time", sa.Time, nullable=False),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("assigned_to_employee_id", sa.BigInteger, nullable=False),
        sa.Column("managed_by_employee_id", sa.BigInteger),
        sa.Column("performance_score", sa.Numeric(3, 1)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="RESTRICT",
            name="fk_tasks_project",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_to_employee_id"],
            ["employees.id"],
            ondelete="RESTRICT",
            name="fk_tasks_assigned_employee",
        ),
        sa.ForeignKeyConstraint(
            ["managed_by_employee_id"],
            ["employees.id"],
            ondelete="SET NULL",
            name="fk_tasks_manager_employee",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'in_progress', 'completed', 'cancelled')",
            name="ck_tasks_status",
        ),
        sa.CheckConstraint(
            "performance_score IS NULL OR "
            "performance_score BETWEEN 0 AND 10",
            name="ck_tasks_performance_score",
        ),
        sa.CheckConstraint(
            "end_time > start_time",
            name="ck_tasks_time_order",
        ),
    )

    op.create_index(
        "ix_tasks_org_assignee",
        "tasks",
        ["organization_id", "assigned_to_employee_id"],
    )
    op.create_index(
        "ix_tasks_org_manager",
        "tasks",
        ["organization_id", "managed_by_employee_id"],
    )
    op.create_index(
        "ix_tasks_org_project_date",
        "tasks",
        ["organization_id", "project_id", "task_date"],
    )
    op.create_index(
        "ix_tasks_org_status",
        "tasks",
        ["organization_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_tasks_org_status", table_name="tasks")
    op.drop_index("ix_tasks_org_project_date", table_name="tasks")
    op.drop_index("ix_tasks_org_manager", table_name="tasks")
    op.drop_index("ix_tasks_org_assignee", table_name="tasks")
    op.drop_table("tasks")
