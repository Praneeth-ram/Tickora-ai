"""Row-level security for the chatbot read role (tickora_agent)."""
from alembic import op

revision = "20261106_rls_policies"
down_revision = "e3c0d4cde409"
branch_labels = None
depends_on = None

AGENT_ROLE = "tickora_agent"

FUNCTIONS = """
CREATE OR REPLACE FUNCTION public.app_can_see_employee(owner_id bigint)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT CASE NULLIF(current_setting('app.role', true), '')
    WHEN 'super_admin' THEN EXISTS (
      SELECT 1 FROM employees e
      WHERE e.id = owner_id
        AND e.organization_id = NULLIF(current_setting('app.organization_id', true), '')::bigint)
    WHEN 'admin' THEN EXISTS (
      SELECT 1 FROM employees e
      WHERE e.id = owner_id
        AND e.organization_id = NULLIF(current_setting('app.organization_id', true), '')::bigint
        AND e.department_id = NULLIF(current_setting('app.department_id', true), '')::bigint)
    WHEN 'employee' THEN
      owner_id = NULLIF(current_setting('app.employee_id', true), '')::bigint
    ELSE false
  END;
$$;

CREATE OR REPLACE FUNCTION public.app_can_see_self_or_org(owner_id bigint)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT CASE NULLIF(current_setting('app.role', true), '')
    WHEN 'super_admin' THEN EXISTS (
      SELECT 1 FROM employees e
      WHERE e.id = owner_id
        AND e.organization_id = NULLIF(current_setting('app.organization_id', true), '')::bigint)
    WHEN 'admin' THEN
      owner_id = NULLIF(current_setting('app.employee_id', true), '')::bigint
    WHEN 'employee' THEN
      owner_id = NULLIF(current_setting('app.employee_id', true), '')::bigint
    ELSE false
  END;
$$;
"""

POLICIES = {
    "employee_schedule_assignments": "app_can_see_employee(employee_id)",
    "attendance_records": "app_can_see_employee(employee_id)",
    "leave_requests": "app_can_see_employee(employee_id)",
    "leave_balances": "app_can_see_employee(employee_id)",
    "wfh_requests": "app_can_see_employee(employee_id)",
    "timesheets": "app_can_see_employee(employee_id)",
    "tasks": "app_can_see_employee(assigned_to_employee_id)",
    "employees": "app_can_see_employee(id)",
    "payroll_summaries": "app_can_see_self_or_org(employee_id)",
    "loan_requests": "app_can_see_self_or_org(employee_id)",
    "holidays": (
        "EXISTS (SELECT 1 FROM holiday_calendars hc "
        "WHERE hc.id = holidays.calendar_id "
        "AND hc.organization_id = NULLIF(current_setting('app.organization_id', true), '')::int)"
    ),
    "leave_types": (
        "organization_id = NULLIF(current_setting('app.organization_id', true), '')::int"
    ),
    "attendance_punches": (
        "EXISTS (SELECT 1 FROM attendance_records a "
        "WHERE a.id = attendance_punches.attendance_id "
        "AND app_can_see_employee(a.employee_id))"
    ),
    "attendance_adjustments": (
        "EXISTS (SELECT 1 FROM attendance_records a "
        "WHERE a.id = attendance_adjustments.attendance_id "
        "AND app_can_see_employee(a.employee_id))"
    ),
}

SCHEDULE_VIEW_PLAIN = """
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
"""


def upgrade() -> None:
    bind = op.get_bind()
    version = bind.exec_driver_sql("SHOW server_version_num").scalar()
    if int(version) < 150000:
        raise RuntimeError("PostgreSQL 15 or later is required for security_invoker views.")

    # Remove any overloads from an earlier attempt.
    op.execute("DROP FUNCTION IF EXISTS public.app_can_see_employee(integer)")
    op.execute("DROP FUNCTION IF EXISTS public.app_can_see_self_or_org(integer)")
    op.execute(FUNCTIONS)

    # The view runs with the caller's rights, so row-level security on its base table applies.
    op.execute("ALTER VIEW public.employee_work_schedules SET (security_invoker = true)")

    for table, using_sql in POLICIES.items():
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS agent_read ON public.{table}")
        op.execute(
            f"CREATE POLICY agent_read ON public.{table} "
            f"FOR SELECT TO {AGENT_ROLE} USING ({using_sql})"
        )


def downgrade() -> None:
    # 1. Restore the view without the function filter, so nothing depends on the functions.
    op.execute(SCHEDULE_VIEW_PLAIN)
    op.execute("ALTER VIEW public.employee_work_schedules RESET (security_invoker)")
    # 2. Remove the policies, which depend on the functions.
    for table in POLICIES:
        op.execute(f"DROP POLICY IF EXISTS agent_read ON public.{table}")
        op.execute(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY")
    # 3. The functions now have no dependents, so they can be dropped.
    op.execute("DROP FUNCTION IF EXISTS public.app_can_see_self_or_org(bigint)")
    op.execute("DROP FUNCTION IF EXISTS public.app_can_see_employee(bigint)")