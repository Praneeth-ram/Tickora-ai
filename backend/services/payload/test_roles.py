import pytest

from backend.services.operation_registry import build_operation_registry
from backend.services.payload.entities import (
    build_specs,
    can_access_entity,
    narratable_for_role,
    registry_for_role,
)

SUPER_ADMIN_ONLY = ["payroll_summary"]
OWN_SCOPED_SENSITIVE = ["loan_request"]
OWN_DATA = ["attendance", "leave_request", "wfh_request", "timesheet", "task"]


@pytest.fixture(scope="module")
def registry():
    return build_operation_registry()


@pytest.fixture(scope="module")
def specs(registry):
    return build_specs(registry)


@pytest.mark.parametrize("role", ["employee", "admin"])
@pytest.mark.parametrize("entity", SUPER_ADMIN_ONLY)
def test_employee_and_admin_cannot_access_super_admin_only_entities(entity, role):
    assert can_access_entity(entity, role) is False


def test_super_admin_can_access_sensitive():
    for entity in SUPER_ADMIN_ONLY + OWN_SCOPED_SENSITIVE:
        assert can_access_entity(entity, "super_admin") is True


@pytest.mark.parametrize("role", ["employee", "admin"])
def test_loan_access_is_available_but_row_scoped(role):
    assert can_access_entity("loan_request", role) is True


@pytest.mark.parametrize("role", ["employee", "admin"])
def test_registry_for_role_removes_sensitive_operations(registry, role):
    filtered = registry_for_role(registry, role)
    assert not any(d["entity"] in SUPER_ADMIN_ONLY for d in filtered.values())
    if any(d["entity"] == "loan_request" for d in registry.values()):
        assert any(d["entity"] == "loan_request" for d in filtered.values())


def test_super_admin_keeps_sensitive_operations(registry):
    filtered = registry_for_role(registry, "super_admin")
    for entity in SUPER_ADMIN_ONLY + OWN_SCOPED_SENSITIVE:
        if any(d["entity"] == entity for d in registry.values()):
            assert any(d["entity"] == entity for d in filtered.values())


@pytest.mark.parametrize("role", ["employee", "admin"])
def test_own_data_stays_available(registry, role):
    filtered = registry_for_role(registry, role)
    for entity in OWN_DATA:
        if any(d["entity"] == entity for d in registry.values()):
            assert any(d["entity"] == entity for d in filtered.values()), entity


def test_unknown_role_is_rejected():
    with pytest.raises(ValueError):
        can_access_entity("attendance", "guest")


def test_narration_blocked_for_employee_and_admin_on_payroll(specs):
    if "payroll_summary" in specs:
        assert narratable_for_role(specs, "payroll_summary", "employee") is False
        assert narratable_for_role(specs, "payroll_summary", "admin") is False


def test_narration_allowed_for_super_admin_on_payroll(specs):
    if "payroll_summary" in specs:
        assert narratable_for_role(specs, "payroll_summary", "super_admin") is True


def test_narration_for_own_attendance_all_roles(specs):
    if "attendance" in specs:
        for role in ["employee", "admin", "super_admin"]:
            assert narratable_for_role(specs, "attendance", role) is True