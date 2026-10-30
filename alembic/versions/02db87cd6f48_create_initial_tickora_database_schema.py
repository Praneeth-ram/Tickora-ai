
"""Create initial Tickora database schema.

Revision ID: 02db87cd6f48
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "02db87cd6f48"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------------------------------------------------------
    # 1. Organization structure
    # ---------------------------------------------------------
    op.create_table(
        "organizations",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("name", sa.String(150), nullable=False, unique=True),
        sa.Column("timezone", sa.String(64), nullable=False,
                  server_default="Asia/Kolkata"),
        sa.Column("country_code", sa.String(2), nullable=False,
                  server_default="IN"),
        sa.Column("is_active", sa.Boolean, nullable=False,
                  server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "departments",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("organization_id", sa.BigInteger,
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.UniqueConstraint("organization_id", "name",
                            name="uq_department_org_name"),
    )

    op.create_table(
        "teams",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("department_id", sa.BigInteger,
                  sa.ForeignKey("departments.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.UniqueConstraint("department_id", "name",
                            name="uq_team_department_name"),
    )

    op.create_table(
        "employees",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("organization_id", sa.BigInteger,
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("department_id", sa.BigInteger,
                  sa.ForeignKey("departments.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("team_id", sa.BigInteger,
                  sa.ForeignKey("teams.id", ondelete="SET NULL")),
        sa.Column("manager_id", sa.BigInteger,
                  sa.ForeignKey("employees.id", ondelete="SET NULL")),
        sa.Column("employee_code", sa.String(30), nullable=False),
        sa.Column("full_name", sa.String(150), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("designation", sa.String(100)),
        sa.Column("employment_type", sa.String(30),
                  nullable=False, server_default="full_time"),
        sa.Column("date_joined", sa.Date, nullable=False),
        sa.Column("date_left", sa.Date),
        sa.Column("is_active", sa.Boolean, nullable=False,
                  server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "employee_code",
                            name="uq_employee_org_code"),
        sa.UniqueConstraint("organization_id", "email",
                            name="uq_employee_org_email"),
        sa.CheckConstraint(
            "date_left IS NULL OR date_left >= date_joined",
            name="ck_employee_employment_dates",
        ),
    )
    op.create_index("ix_employees_department", "employees", ["department_id"])
    op.create_index("ix_employees_manager", "employees", ["manager_id"])

    # ---------------------------------------------------------
    # 2. Work schedules
    # ---------------------------------------------------------
    op.create_table(
        "work_schedules",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("organization_id", sa.BigInteger,
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("schedule_type", sa.String(30),
                  nullable=False, server_default="fixed"),
        sa.Column("is_active", sa.Boolean, nullable=False,
                  server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "schedule_days",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("schedule_id", sa.BigInteger,
                  sa.ForeignKey("work_schedules.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("day_of_week", sa.SmallInteger, nullable=False),
        sa.Column("start_time", sa.Time),
        sa.Column("end_time", sa.Time),
        sa.Column("break_minutes", sa.Integer, nullable=False,
                  server_default="0"),
        sa.Column("required_minutes", sa.Integer, nullable=False,
                  server_default="480"),
        sa.Column("is_working_day", sa.Boolean, nullable=False,
                  server_default=sa.true()),
        sa.UniqueConstraint("schedule_id", "day_of_week",
                            name="uq_schedule_day"),
        sa.CheckConstraint("day_of_week BETWEEN 0 AND 6",
                           name="ck_schedule_day_of_week"),
        sa.CheckConstraint("required_minutes >= 0",
                           name="ck_schedule_required_minutes"),
        sa.CheckConstraint("break_minutes >= 0",
                           name="ck_schedule_break_minutes"),
    )

    op.create_table(
        "employee_schedule_assignments",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("employee_id", sa.BigInteger,
                  sa.ForeignKey("employees.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("schedule_id", sa.BigInteger,
                  sa.ForeignKey("work_schedules.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("effective_from", sa.Date, nullable=False),
        sa.Column("effective_to", sa.Date),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_schedule_assignment_dates",
        ),
    )
    op.create_index(
        "ix_schedule_assignment_employee_dates",
        "employee_schedule_assignments",
        ["employee_id", "effective_from", "effective_to"],
    )

    # ---------------------------------------------------------
    # 3. Holidays
    # ---------------------------------------------------------
    op.create_table(
        "holiday_calendars",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("organization_id", sa.BigInteger,
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("region", sa.String(100)),
        sa.UniqueConstraint("organization_id", "name",
                            name="uq_holiday_calendar_org_name"),
    )

    op.create_table(
        "holidays",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("calendar_id", sa.BigInteger,
                  sa.ForeignKey("holiday_calendars.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("holiday_date", sa.Date, nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("holiday_type", sa.String(30),
                  nullable=False, server_default="public"),
        sa.UniqueConstraint("calendar_id", "holiday_date", "name",
                            name="uq_holiday_calendar_date_name"),
    )
    op.create_index("ix_holidays_date", "holidays", ["holiday_date"])

    op.create_table(
        "employee_holiday_assignments",
        sa.Column("employee_id", sa.BigInteger,
                  sa.ForeignKey("employees.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("calendar_id", sa.BigInteger,
                  sa.ForeignKey("holiday_calendars.id", ondelete="CASCADE"),
                  primary_key=True),
    )

    # ---------------------------------------------------------
    # 4. Attendance and punches
    # ---------------------------------------------------------
    op.create_table(
        "attendance_records",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("employee_id", sa.BigInteger,
                  sa.ForeignKey("employees.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("attendance_date", sa.Date, nullable=False),
        sa.Column("schedule_id", sa.BigInteger,
                  sa.ForeignKey("work_schedules.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("clock_in", sa.DateTime(timezone=True)),
        sa.Column("clock_out", sa.DateTime(timezone=True)),
        sa.Column("worked_minutes", sa.Integer, nullable=False,
                  server_default="0"),
        sa.Column("regular_minutes", sa.Integer, nullable=False,
                  server_default="0"),
        sa.Column("overtime_minutes", sa.Integer, nullable=False,
                  server_default="0"),
        sa.Column("break_minutes", sa.Integer, nullable=False,
                  server_default="0"),
        sa.Column("is_late", sa.Boolean, nullable=False,
                  server_default=sa.false()),
        sa.Column("work_location", sa.String(30),
                  nullable=False, server_default="office"),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("employee_id", "attendance_date",
                            name="uq_attendance_employee_date"),
        sa.CheckConstraint(
            "status IN ('present','absent','late','half_day',"
            "'on_leave','holiday','weekend','work_from_home','incomplete')",
            name="ck_attendance_status",
        ),
        sa.CheckConstraint("worked_minutes >= 0",
                           name="ck_attendance_worked_minutes"),
        sa.CheckConstraint("regular_minutes >= 0",
                           name="ck_attendance_regular_minutes"),
        sa.CheckConstraint("overtime_minutes >= 0",
                           name="ck_attendance_overtime_minutes"),
        sa.CheckConstraint("break_minutes >= 0",
                           name="ck_attendance_break_minutes"),
        sa.CheckConstraint(
            "clock_out IS NULL OR clock_in IS NULL OR clock_out >= clock_in",
            name="ck_attendance_clock_order",
        ),
    )
    op.create_index(
        "ix_attendance_date_status",
        "attendance_records",
        ["attendance_date", "status"],
    )
    op.create_index(
        "ix_attendance_employee_date",
        "attendance_records",
        ["employee_id", "attendance_date"],
    )

    op.create_table(
        "attendance_punches",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("attendance_id", sa.BigInteger,
                  sa.ForeignKey("attendance_records.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("punched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("punch_type", sa.String(20), nullable=False),
        sa.Column("source", sa.String(30),
                  nullable=False, server_default="mobile"),
        sa.Column("location_description", sa.String(200)),
        sa.CheckConstraint(
            "punch_type IN ('clock_in','clock_out','break_start','break_end')",
            name="ck_punch_type",
        ),
    )
    op.create_index(
        "ix_attendance_punches_parent_time",
        "attendance_punches",
        ["attendance_id", "punched_at"],
    )

    op.create_table(
        "attendance_adjustments",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("attendance_id", sa.BigInteger,
                  sa.ForeignKey("attendance_records.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("old_values", sa.JSON),
        sa.Column("new_values", sa.JSON),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
    )

    # ---------------------------------------------------------
    # 5. Leave
    # ---------------------------------------------------------
    op.create_table(
        "leave_types",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("organization_id", sa.BigInteger,
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("is_paid", sa.Boolean, nullable=False,
                  server_default=sa.true()),
        sa.UniqueConstraint("organization_id", "code",
                            name="uq_leave_type_org_code"),
    )

    op.create_table(
        "leave_balances",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("employee_id", sa.BigInteger,
                  sa.ForeignKey("employees.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("leave_type_id", sa.BigInteger,
                  sa.ForeignKey("leave_types.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("allocated_days", sa.Numeric(6, 2), nullable=False,
                  server_default="0"),
        sa.Column("used_days", sa.Numeric(6, 2), nullable=False,
                  server_default="0"),
        sa.Column("pending_days", sa.Numeric(6, 2), nullable=False,
                  server_default="0"),
        sa.UniqueConstraint("employee_id", "leave_type_id", "year",
                            name="uq_leave_balance_employee_type_year"),
        sa.CheckConstraint("allocated_days >= 0",
                           name="ck_leave_allocated"),
        sa.CheckConstraint("used_days >= 0",
                           name="ck_leave_used"),
        sa.CheckConstraint("pending_days >= 0",
                           name="ck_leave_pending"),
    )

    op.create_table(
        "leave_requests",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("employee_id", sa.BigInteger,
                  sa.ForeignKey("employees.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("leave_type_id", sa.BigInteger,
                  sa.ForeignKey("leave_types.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=False),
        sa.Column("requested_days", sa.Numeric(6, 2), nullable=False),
        sa.Column("reason", sa.Text),
        sa.Column("status", sa.String(20), nullable=False,
                  server_default="pending"),
        sa.Column("applied_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("end_date >= start_date",
                           name="ck_leave_request_dates"),
        sa.CheckConstraint("requested_days > 0",
                           name="ck_leave_requested_days"),
        sa.CheckConstraint(
            "status IN ('pending','approved','rejected','cancelled')",
            name="ck_leave_request_status",
        ),
    )
    op.create_index(
        "ix_leave_employee_status_dates",
        "leave_requests",
        ["employee_id", "status", "start_date"],
    )

    op.create_table(
        "leave_approvals",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("leave_request_id", sa.BigInteger,
                  sa.ForeignKey("leave_requests.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("approver_id", sa.BigInteger,
                  sa.ForeignKey("employees.id", ondelete="SET NULL")),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("comments", sa.Text),
        sa.Column("decided_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "decision IN ('approved','rejected','returned')",
            name="ck_leave_approval_decision",
        ),
    )

    # ---------------------------------------------------------
    # 6. Work from home
    # ---------------------------------------------------------
    op.create_table(
        "wfh_requests",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("employee_id", sa.BigInteger,
                  sa.ForeignKey("employees.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=False),
        sa.Column("reason", sa.Text),
        sa.Column("status", sa.String(20), nullable=False,
                  server_default="pending"),
        sa.Column("applied_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("end_date >= start_date",
                           name="ck_wfh_dates"),
        sa.CheckConstraint(
            "status IN ('pending','approved','rejected','cancelled')",
            name="ck_wfh_status",
        ),
    )
    op.create_index(
        "ix_wfh_employee_status_dates",
        "wfh_requests",
        ["employee_id", "status", "start_date"],
    )

    op.create_table(
        "wfh_approvals",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("wfh_request_id", sa.BigInteger,
                  sa.ForeignKey("wfh_requests.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("approver_id", sa.BigInteger,
                  sa.ForeignKey("employees.id", ondelete="SET NULL")),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("comments", sa.Text),
        sa.Column("decided_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "decision IN ('approved','rejected','returned')",
            name="ck_wfh_approval_decision",
        ),
    )

    # ---------------------------------------------------------
    # 7. Projects and timesheets
    # ---------------------------------------------------------
    op.create_table(
        "projects",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("organization_id", sa.BigInteger,
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False,
                  server_default=sa.true()),
        sa.UniqueConstraint("organization_id", "code",
                            name="uq_project_org_code"),
    )

    op.create_table(
        "timesheets",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("employee_id", sa.BigInteger,
                  sa.ForeignKey("employees.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),
        sa.Column("status", sa.String(20), nullable=False,
                  server_default="draft"),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("period_end >= period_start",
                           name="ck_timesheet_period"),
        sa.CheckConstraint(
            "status IN ('draft','submitted','approved','rejected')",
            name="ck_timesheet_status",
        ),
    )
    op.create_index(
        "ix_timesheet_employee_period",
        "timesheets",
        ["employee_id", "period_start", "period_end"],
    )

    op.create_table(
        "timesheet_entries",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("timesheet_id", sa.BigInteger,
                  sa.ForeignKey("timesheets.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("project_id", sa.BigInteger,
                  sa.ForeignKey("projects.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("work_date", sa.Date, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("worked_minutes", sa.Integer, nullable=False),
        sa.CheckConstraint("worked_minutes >= 0",
                           name="ck_timesheet_entry_minutes"),
    )
    op.create_index(
        "ix_timesheet_entry_date",
        "timesheet_entries",
        ["work_date"],
    )

    # ---------------------------------------------------------
    # 8. Payroll summaries (synthetic development data only)
    # ---------------------------------------------------------
    op.create_table(
        "payroll_periods",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("organization_id", sa.BigInteger,
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),
        sa.UniqueConstraint("organization_id", "period_start", "period_end",
                            name="uq_payroll_period_org_dates"),
        sa.CheckConstraint("period_end >= period_start",
                           name="ck_payroll_period_dates"),
    )

    op.create_table(
        "payroll_summaries",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("payroll_period_id", sa.BigInteger,
                  sa.ForeignKey("payroll_periods.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("employee_id", sa.BigInteger,
                  sa.ForeignKey("employees.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("gross_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("deduction_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("net_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False,
                  server_default="INR"),
        sa.UniqueConstraint("payroll_period_id", "employee_id",
                            name="uq_payroll_summary_employee_period"),
        sa.CheckConstraint("gross_amount >= 0",
                           name="ck_payroll_gross"),
        sa.CheckConstraint("deduction_amount >= 0",
                           name="ck_payroll_deductions"),
        sa.CheckConstraint("net_amount >= 0",
                           name="ck_payroll_net"),
    )

    # ---------------------------------------------------------
    # 9. AI business definitions and conversation history
    # ---------------------------------------------------------
    op.create_table(
        "business_metrics",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("metric_key", sa.String(80), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("calculation_definition", sa.Text, nullable=False),
        sa.Column("is_enabled", sa.Boolean, nullable=False,
                  server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "conversation_sessions",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("employee_id", sa.BigInteger,
                  sa.ForeignKey("employees.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("last_activity_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_conversation_employee_activity",
        "conversation_sessions",
        ["employee_id", "last_activity_at"],
    )

    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("session_id", sa.BigInteger,
                  sa.ForeignKey("conversation_sessions.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "role IN ('user','assistant','system')",
            name="ck_conversation_message_role",
        ),
    )
    op.create_index(
        "ix_conversation_messages_session_time",
        "conversation_messages",
        ["session_id", "created_at"],
    )

    op.create_table(
        "query_audit_logs",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("employee_id", sa.BigInteger,
                  sa.ForeignKey("employees.id", ondelete="SET NULL")),
        sa.Column("operation_id", sa.String(100)),
        sa.Column("query_plan", sa.JSON),
        sa.Column("success", sa.Boolean, nullable=False),
        sa.Column("error_code", sa.String(80)),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_query_audit_created_at", "query_audit_logs",
                    ["created_at"])

    op.create_table(
        "user_feedback",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("employee_id", sa.BigInteger,
                  sa.ForeignKey("employees.id", ondelete="SET NULL")),
        sa.Column("message_id", sa.BigInteger,
                  sa.ForeignKey("conversation_messages.id", ondelete="SET NULL")),
        sa.Column("rating", sa.SmallInteger),
        sa.Column("feedback_text", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "rating IS NULL OR rating BETWEEN 1 AND 5",
            name="ck_feedback_rating",
        ),
    )


def downgrade() -> None:
    # Reverse dependency order. This removes schema objects, not the database.
    op.drop_table("user_feedback")
    op.drop_index("ix_query_audit_created_at", table_name="query_audit_logs")
    op.drop_table("query_audit_logs")
    op.drop_index(
        "ix_conversation_messages_session_time",
        table_name="conversation_messages",
    )
    op.drop_table("conversation_messages")
    op.drop_index(
        "ix_conversation_employee_activity",
        table_name="conversation_sessions",
    )
    op.drop_table("conversation_sessions")
    op.drop_table("business_metrics")
    op.drop_table("payroll_summaries")
    op.drop_table("payroll_periods")
    op.drop_index("ix_timesheet_entry_date", table_name="timesheet_entries")
    op.drop_table("timesheet_entries")
    op.drop_index("ix_timesheet_employee_period", table_name="timesheets")
    op.drop_table("timesheets")
    op.drop_table("projects")
    op.drop_table("wfh_approvals")
    op.drop_index("ix_wfh_employee_status_dates", table_name="wfh_requests")
    op.drop_table("wfh_requests")
    op.drop_table("leave_approvals")
    op.drop_index(
        "ix_leave_employee_status_dates",
        table_name="leave_requests",
    )
    op.drop_table("leave_requests")
    op.drop_table("leave_balances")
    op.drop_table("leave_types")
    op.drop_table("attendance_adjustments")
    op.drop_index(
        "ix_attendance_punches_parent_time",
        table_name="attendance_punches",
    )
    op.drop_table("attendance_punches")
    op.drop_index("ix_attendance_employee_date", table_name="attendance_records")
    op.drop_index("ix_attendance_date_status", table_name="attendance_records")
    op.drop_table("attendance_records")
    op.drop_index(
        "ix_schedule_assignment_employee_dates",
        table_name="employee_schedule_assignments",
    )
    op.drop_table("employee_schedule_assignments")
    op.drop_table("schedule_days")
    op.drop_table("work_schedules")
    op.drop_table("employee_holiday_assignments")
    op.drop_index("ix_holidays_date", table_name="holidays")
    op.drop_table("holidays")
    op.drop_table("holiday_calendars")
    op.drop_index("ix_employees_manager", table_name="employees")
    op.drop_index("ix_employees_department", table_name="employees")
    op.drop_table("employees")
    op.drop_table("teams")
    op.drop_table("departments")
    op.drop_table("organizations")
