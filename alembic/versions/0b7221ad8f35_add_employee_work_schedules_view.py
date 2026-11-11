"""add employee_work_schedules view

Revision ID: 0b7221ad8f35
Revises: 20261104_add_roles
Create Date: 2026-11-10 18:17:58.493167

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0b7221ad8f35"
down_revision: Union[str, None] = "20261104_add_roles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
CREATE OR REPLACE VIEW public.employee_work_schedules AS
SELECT
    esa.employee_id,
    ws.name AS schedule_name,
    esa.effective_from,
    esa.effective_to,
    MIN(sd.start_time) AS shift_start,
    MAX(sd.end_time) AS shift_end,
    ROUND(
        AVG(sd.required_minutes) FILTER (WHERE sd.is_working_day) / 60.0,
        1
    ) AS expected_hours,
    ARRAY_AGG(((sd.day_of_week + 6) % 7) + 1
              ORDER BY ((sd.day_of_week + 6) % 7) + 1)
        FILTER (WHERE sd.is_working_day) AS workdays
FROM public.employee_schedule_assignments AS esa
JOIN public.work_schedules AS ws
    ON ws.id = esa.schedule_id AND ws.is_active = TRUE
LEFT JOIN public.schedule_days AS sd
    ON sd.schedule_id = ws.id
GROUP BY esa.employee_id, ws.name, esa.effective_from, esa.effective_to
""")

    op.execute("""
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tickora_agent') THEN
        GRANT SELECT ON public.employee_work_schedules TO tickora_agent;
    END IF;
END $$;
""")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS public.employee_work_schedules")