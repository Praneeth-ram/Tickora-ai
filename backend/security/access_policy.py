"""Role-based, read-only row access for the chatbot.
super_admin: any employee in the organization, all entities.
admin:       employees in their own department for operational data;
             their own payroll and loans only.
employee:    their own records only.

Default deny: an entity or field not listed here is refused.
"""
import logging
from contextvars import ContextVar
from dataclasses import dataclass
from sqlalchemy import text
from backend.exceptions import ForbiddenError

audit = logging.getLogger("audit")

SUPER_ADMIN = "super_admin"
ADMIN = "admin"
EMPLOYEE = "employee"
ROLES = frozenset({SUPER_ADMIN, ADMIN, EMPLOYEE})

REFUSAL_MESSAGE = (
    "I can only show your own records. I can't access another employee's "
    "attendance, leave, or other details."
)

# Scope per role: "self", "department", or "org".
_OPERATIONAL = {EMPLOYEE: "self", ADMIN: "department", SUPER_ADMIN: "org"}
_SENSITIVE = {EMPLOYEE: "self", ADMIN: "self", SUPER_ADMIN: "org"}
_ORG_WIDE = {EMPLOYEE: "org", ADMIN: "org", SUPER_ADMIN: "org"}

ENTITY_RULES = {
    "attendance": {"owned": True, "scopes": _OPERATIONAL},
    "attendance_punch": {"owned": True, "scopes": _OPERATIONAL},
    "attendance_adjustment": {"owned": True, "scopes": _OPERATIONAL},
    "leave_request": {"owned": True, "scopes": _OPERATIONAL},
    "leave_balance": {"owned": True, "scopes": _OPERATIONAL},
    "wfh_request": {"owned": True, "scopes": _OPERATIONAL},
    "timesheet": {"owned": True, "scopes": _OPERATIONAL},
    "task": {"owned": True, "scopes": _OPERATIONAL},
    "payroll_summary": {"owned": True, "scopes": _SENSITIVE},
    "loan_request": {"owned": True, "scopes": _SENSITIVE},
    "holiday": {"owned": False, "scopes": _ORG_WIDE},
    "leave_type": {"owned": False, "scopes": _ORG_WIDE},
    "work_schedule": {"owned": True, "scopes": _OPERATIONAL},
    "employee_directory": {
        "owned": True,
        "scopes": {ADMIN: "department", SUPER_ADMIN: "org"},
    },
}

# Column that names the employee a row belongs to, when not employee_id.
OWNER_COLUMNS = {"task": "assigned_to_employee_id"}

# Fields only a super admin may read.
SUPER_ADMIN_ONLY_FIELDS = frozenset({"performance_score", "remarks"})

class AccessDenied(Exception):
    """The actor's role does not allow the requested data."""

    def __init__(self) -> None:
        super().__init__(REFUSAL_MESSAGE)

@dataclass(frozen=True)
class Actor:
    employee_id: int
    organization_id: int
    department_id: int | None
    role: str

    def __post_init__(self) -> None:
        if self.role not in ROLES:
            raise ValueError(f"Unknown role: {self.role}")


_current_actor: ContextVar[Actor | None] = ContextVar("current_actor", default=None)

def set_actor(actor: Actor):
    return _current_actor.set(actor)

def reset_actor(token) -> None:
    _current_actor.reset(token)

def get_actor() -> Actor | None:
    return _current_actor.get()

def load_actor(connection, employee_id: int, employee_code: str) -> Actor:
    """Read the actor's role and scope from the database on every request."""
    row = connection.execute(
        text("""
            SELECT id, organization_id, department_id, role
            FROM public.employees
            WHERE id = :employee_id
              AND employee_code = :employee_code
              AND is_active = TRUE
        """),
        {"employee_id": employee_id, "employee_code": employee_code},
    ).mappings().one_or_none()
    if row is None:
        raise ForbiddenError(REFUSAL_MESSAGE)
    return Actor(
        employee_id=row["id"],
        organization_id=row["organization_id"],
        department_id=row["department_id"],
        role=row["role"],
    )

def authorize_entity(actor: Actor, entity: str) -> str:
    """Return the scope for this actor and entity, or deny."""
    rule = ENTITY_RULES.get(entity)
    scope = rule["scopes"].get(actor.role) if rule else None
    audit.info(
        "role=%s employee_id=%s entity=%s decision=%s",
        actor.role, actor.employee_id, entity,
        "allowed" if scope else "denied",
    )
    if scope is None:
        raise AccessDenied()
    return scope

def check_fields(actor: Actor, fields) -> None:
    if SUPER_ADMIN_ONLY_FIELDS.intersection(fields) and actor.role != SUPER_ADMIN:
        raise AccessDenied()

def visible_fields(actor: Actor, fields) -> list[str]:
    """Drop super-admin-only fields from default field lists for other roles."""
    if actor.role == SUPER_ADMIN:
        return list(fields)
    return [field for field in fields if field not in SUPER_ADMIN_ONLY_FIELDS]

def owner_column(entity: str) -> str:
    return OWNER_COLUMNS.get(entity, "employee_id")

def scope_clause(actor: Actor, entity: str, owner_sql: str) -> tuple[str, dict]:
    """Return the SQL row filter and its parameters for this actor and entity."""
    scope = authorize_entity(actor, entity)
    if not ENTITY_RULES[entity]["owned"]:
        return "", {}

    if scope == "self":
        return (
            f"{owner_sql} = :actor_employee_id",
            {"actor_employee_id": actor.employee_id},
        )

    if scope == "department":
        if actor.department_id is None:
            return "FALSE", {}
        return (
            f"{owner_sql} IN (SELECT e.id FROM public.employees e "
            "WHERE e.department_id = :actor_department_id "
            "AND e.organization_id = :actor_organization_id)",
            {
                "actor_department_id": actor.department_id,
                "actor_organization_id": actor.organization_id,
            },
        )

    return (
        f"{owner_sql} IN (SELECT e.id FROM public.employees e "
        "WHERE e.organization_id = :actor_organization_id)",
        {"actor_organization_id": actor.organization_id},
    )

_current_subject: ContextVar[int | None] = ContextVar("current_subject", default=None)


def set_subject(employee_id: int):
    return _current_subject.set(employee_id)


def reset_subject(token) -> None:
    _current_subject.reset(token)


def get_subject() -> int | None:
    return _current_subject.get()

def subject_name(connection, employee_id: int) -> str | None:
    row = connection.execute(
        text("SELECT full_name FROM public.employees WHERE id = :id AND is_active = TRUE"),
        {"id": employee_id},
    ).scalar_one_or_none()
    return row

from contextlib import contextmanager

@contextmanager
def scoped_connection(engine, actor: Actor):
    """Open one transaction with the actor set. RLS reads these settings for every query in it."""
    with engine.begin() as connection:
        connection.execute(
            text("""
                SELECT set_config('app.employee_id', :emp, true),
                       set_config('app.role', :role, true),
                       set_config('app.department_id', :dept, true),
                       set_config('app.organization_id', :org, true)
            """),
            {
                "emp": str(actor.employee_id),
                "role": actor.role,
                "dept": "" if actor.department_id is None else str(actor.department_id),
                "org": str(actor.organization_id),
            },
        )
        yield connection