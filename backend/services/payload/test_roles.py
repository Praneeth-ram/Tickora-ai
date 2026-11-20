import pytest

from backend.services.operation_registry import build_operation_registry, get_model_catalog
from backend.services.payload.entities import (
    build_specs,
    can_access_entity,
    narratable_for_role,
    registry_for_role,
)

# Own-scoped sensitive entities: every role has a scope; rows are limited by ownership.
OWN_SCOPED_SENSITIVE = ["payroll_summary", "loan_request"]
OWN_DATA = ["attendance", "leave_request", "wfh_request", "timesheet", "task"]
ALL_ROLES = ["employee", "admin", "super_admin"]


@pytest.fixture(scope="module")
def registry():
    return build_operation_registry()


@pytest.fixture(scope="module")
def specs(registry):
    return build_specs(registry)


@pytest.mark.parametrize("role", ALL_ROLES)
@pytest.mark.parametrize("entity", OWN_SCOPED_SENSITIVE)
def test_sensitive_entities_have_a_scope_for_every_role(entity, role):
    assert can_access_entity(entity, role) is True


@pytest.mark.parametrize("role", ALL_ROLES)
def test_registry_for_role_keeps_sensitive_operations(registry, role):
    filtered = registry_for_role(registry, role)
    for entity in OWN_SCOPED_SENSITIVE:
        if any(d["entity"] == entity for d in registry.values()):
            assert any(d["entity"] == entity for d in filtered.values()), (role, entity)


@pytest.mark.parametrize("role", ALL_ROLES)
def test_own_data_stays_available(registry, role):
    filtered = registry_for_role(registry, role)
    for entity in OWN_DATA:
        if any(d["entity"] == entity for d in registry.values()):
            assert any(d["entity"] == entity for d in filtered.values()), (role, entity)


def test_unknown_role_is_rejected():
    with pytest.raises(ValueError):
        can_access_entity("attendance", "guest")


def test_payroll_is_not_narrated_for_employee_or_admin(specs):
    if "payroll_summary" in specs:
        assert narratable_for_role(specs, "payroll_summary", "employee") is False
        assert narratable_for_role(specs, "payroll_summary", "admin") is False


def test_payroll_is_narrated_only_for_super_admin(specs):
    if "payroll_summary" in specs:
        assert narratable_for_role(specs, "payroll_summary", "super_admin") is True


def test_own_attendance_is_narrated_for_all_roles(specs):
    if "attendance" in specs:
        for role in ALL_ROLES:
            assert narratable_for_role(specs, "attendance", role) is True


@pytest.mark.parametrize("role", ["employee", "admin"])
def test_catalog_includes_own_sensitive_entities(registry, role):
    entities = {op["entity"] for op in get_model_catalog(registry, role)}
    for entity in OWN_SCOPED_SENSITIVE:
        if any(d["entity"] == entity for d in registry.values()):
            assert entity in entities, (role, entity)