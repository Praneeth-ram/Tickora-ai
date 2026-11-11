"""add workdays label to employee_work_schedules

Revision ID: e3c0d4cde409
Revises: 0b7221ad8f35
Create Date: 2026-11-11 10:13:14.983424

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e3c0d4cde409'
down_revision: Union[str, None] = '0b7221ad8f35'
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
        FILTER (WHERE sd.is_working_day) AS workdays,
    ARRAY_TO_STRING(
        ARRAY_AGG(
            (ARRAY['Monday','Tuesday','Wednesday','Thursday',
                   'Friday','Saturday','Sunday'])[((sd.day_of_week + 6) % 7) + 1]
            ORDER BY ((sd.day_of_week + 6) % 7) + 1
        ) FILTER (WHERE sd.is_working_day),
        ', '
    ) AS workdays_label
FROM public.employee_schedule_assignments AS esa
JOIN public.work_schedules AS ws
    ON ws.id = esa.schedule_id AND ws.is_active = TRUE
LEFT JOIN public.schedule_days AS sd
    ON sd.schedule_id = ws.id
GROUP BY esa.employee_id, ws.name, esa.effective_from, esa.effective_to
""")


def downgrade() -> None:
    pass