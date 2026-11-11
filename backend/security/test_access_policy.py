import pytest

from backend.security.access_policy import (
    ADMIN, EMPLOYEE, SUPER_ADMIN, Actor, AccessDenied,
    authorize_entity, check_fields, scope_clause,
)


def actor(role, department_id=2):
    return Actor(employee_id=1, organization_id=1, department_id=department_id, role=role)


def test_employee_sees_only_own_attendance():
    sql, params = scope_clause(actor(EMPLOYEE), "attendance", "employee_id")
    assert sql == "employee_id = :actor_employee_id"
    assert params == {"actor_employee_id": 1}


def test_admin_attendance_is_department_scoped():
    sql, params = scope_clause(actor(ADMIN), "attendance", "employee_id")
    assert "department_id = :actor_department_id" in sql
    assert params["actor_department_id"] == 2


def test_admin_payroll_is_own_only():
    sql, _ = scope_clause(actor(ADMIN), "payroll_summary", "employee_id")
    assert sql == "employee_id = :actor_employee_id"


def test_admin_loans_are_own_only():
    sql, _ = scope_clause(actor(ADMIN), "loan_request", "employee_id")
    assert sql == "employee_id = :actor_employee_id"


def test_super_admin_payroll_is_organization_wide():
    sql, params = scope_clause(actor(SUPER_ADMIN), "payroll_summary", "employee_id")
    assert "organization_id = :actor_organization_id" in sql
    assert params == {"actor_organization_id": 1}


def test_admin_without_department_sees_no_departmental_data():
    sql, params = scope_clause(actor(ADMIN, department_id=None), "attendance", "employee_id")
    assert sql == "FALSE" and params == {}


def test_holiday_is_not_owner_scoped():
    assert scope_clause(actor(EMPLOYEE), "holiday", "") == ("", {})


def test_unknown_entity_is_denied():
    with pytest.raises(AccessDenied):
        authorize_entity(actor(SUPER_ADMIN), "employee_salary_secret")


def test_performance_score_is_super_admin_only():
    with pytest.raises(AccessDenied):
        check_fields(actor(ADMIN), ["performance_score"])
    check_fields(actor(SUPER_ADMIN), ["performance_score"])


def test_invalid_role_is_rejected():
    with pytest.raises(ValueError):
        Actor(1, 1, None, "root")