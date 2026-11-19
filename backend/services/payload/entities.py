from typing import Any
from backend.security.access_policy import ADMIN, EMPLOYEE, SUPER_ADMIN

ROLES = {EMPLOYEE, ADMIN, SUPER_ADMIN}

# Never sent to the model, whatever the entity.
EXCLUDED_FIELDS = {"reason", "remarks", "description", "notes"}

# Display labels only. Fields, operations, dates, and scopes come from the registry.
ENTITY_LABELS: dict[str, dict[str, Any]] = {
    "attendance": {
        "label": "attendance", "unit": "days",
        "fields": {
            "attendance_date": "date", "clock_in": "clock in", "clock_out": "clock out",
            "status": "status", "work_location": "work location",
            "worked_minutes": "worked time", "overtime_minutes": "overtime", "is_late": "late",
        },
    },
    "attendance_punch": {
        "label": "clock punch", "unit": "punches",
        "fields": {"punched_at": "time", "punch_type": "type", "source": "source"},
    },
    "attendance_adjustment": {
        "label": "attendance adjustment", "unit": "adjustments",
        "fields": {"created_at": "created on"},
    },
    "leave_request": {
        "label": "leave request", "unit": "requests",
        "fields": {
            "start_date": "start date", "end_date": "end date",
            "requested_days": "days requested", "status": "status", "applied_at": "applied on",
        },
    },
    "leave_balance": {
        "label": "leave balance", "unit": "days",
        "fields": {
            "year": "year", "leave_type_id": "leave type", "allocated_days": "allocated",
            "used_days": "used", "pending_days": "pending",
        },
    },
    "leave_type": {
        "label": "leave type", "unit": "types",
        "fields": {"code": "code", "name": "name", "is_paid": "paid"},
    },
    "wfh_request": {
        "label": "work from home request", "unit": "requests",
        "fields": {"start_date": "start date", "end_date": "end date",
                   "status": "status", "applied_at": "applied on"},
    },
    "timesheet": {
        "label": "timesheet", "unit": "timesheets",
        "fields": {"period_start": "period start", "period_end": "period end",
                   "status": "status", "submitted_at": "submitted on", "approved_at": "approved on"},
    },
    "holiday": {
        "label": "holiday", "unit": "holidays",
        "fields": {"holiday_date": "date", "name": "name", "holiday_type": "type"},
    },
    "task": {
        "label": "task", "unit": "tasks",
        "fields": {"task_date": "date", "title": "title", "status": "status",
                   "start_time": "start time", "end_time": "end time",
                   "performance_score": "performance score"},
    },
    "loan_request": {
        "label": "loan", "unit": "loans", "sensitive": True,
        "fields": {"start_month": "start month", "component": "component", "mode": "mode",
                   "status": "status", "loan_status": "loan status",
                   "total_amount": "total amount", "deducted_amount": "deducted",
                   "remaining_amount": "remaining", "installment_amount": "installment",
                   "installments": "installments", "installments_paid": "installments paid"},
    },
    "work_schedule": {
        "label": "work schedule", "unit": "schedules",
        "fields": {"schedule_name": "schedule", "shift_start": "shift start",
                   "shift_end": "shift end", "expected_hours": "expected hours",
                   "workdays_label": "workdays", "effective_from": "effective from"},
    },
    "payroll_summary": {
        "label": "payroll", "unit": "payslips", "sensitive": True,
        "fields": {"employee_name": "employee", "period_start": "period start",
                   "period_end": "period end", "gross_amount": "gross amount",
                   "deduction_amount": "deductions", "net_amount": "net amount",
                   "currency": "currency"},
    },
}


def build_specs(registry: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Build one spec per registry entity. Entities without labels are never narrated."""
    specs: dict[str, dict[str, Any]] = {}

    for op_id, definition in registry.items():
        entity = definition["entity"]
        if entity not in ENTITY_LABELS or definition["operation"] != "list":
            continue
        if entity in specs:
            continue

        labels = ENTITY_LABELS[entity]
        allowed = {
            f: lbl for f, lbl in labels["fields"].items()
            if f in definition["fields"] and f not in EXCLUDED_FIELDS
        }
        scope = definition["scope"]
        sensitive = labels.get("sensitive", False)

        specs[entity] = {
            "label": labels["label"],
            "unit": labels["unit"],
            "table": definition["table"],
            "scope": scope,
            "date_field": definition["date_field"],
            "field_labels": allowed,
            "operations": sorted(
                other for other, d in registry.items() if d["entity"] == entity
            ),
            "sensitive": sensitive,
            # Narrate only when scope is owner-bound and the data is not sensitive.
            "narratable": (not sensitive) and scope != "employee_organization",
        }

    return specs


def safe_fields(specs: dict[str, dict[str, Any]], entity: str, fields: list[str]) -> list[str]:
    """Return only fields that have a label and are not excluded."""
    if entity not in specs:
        raise KeyError(f"No narration spec for entity {entity!r}")
    allowed = specs[entity]["field_labels"]
    return [f for f in fields if f in allowed]


ROLES = {"employee", "admin", "super_admin"}
# Payroll is unavailable outside the super-admin role. Loan rows remain
# available to all roles, with row ownership enforced by the query policy.
SUPER_ADMIN_ONLY = {"payroll_summary"}

def can_access_entity(entity: str, role: str) -> bool:
    if role not in ROLES:
        raise ValueError(f"Unknown role: {role!r}")
    if entity in SUPER_ADMIN_ONLY:
        return role == "super_admin"
    return True


def registry_for_role(registry: dict[str, dict], role: str) -> dict[str, dict]:
    """Drop every operation the role may not use. Apply before the planner catalog is built."""
    return {
        op_id: definition
        for op_id, definition in registry.items()
        if can_access_entity(definition["entity"], role)
    }


def narratable_for_role(specs: dict[str, dict], entity: str, role: str) -> bool:
    """Narration is allowed only for entities the role can access."""
    if entity not in specs or not can_access_entity(entity, role):
        return False
    spec = specs[entity]
    # Organization-wide scope is safe to narrate only for super admin.
    if spec["scope"] == "employee_organization":
        return role == "super_admin"
    return True