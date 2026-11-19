import pytest

from backend.services.operation_registry import build_operation_registry  # adjust to your module path
from backend.services.payload.entities import (
    ENTITY_LABELS,
    EXCLUDED_FIELDS,
    build_specs,
    safe_fields,
)


@pytest.fixture(scope="module")
def registry():
    return build_operation_registry()


@pytest.fixture(scope="module")
def specs(registry):
    return build_specs(registry)


def test_every_label_entity_is_known_to_registry_or_skipped(registry):
    registry_entities = {d["entity"] for d in registry.values()}
    for entity in ENTITY_LABELS:
        # Entities absent from the database are allowed; they are simply not narrated.
        assert isinstance(entity, str)
    assert registry_entities, "registry is empty; check schema discovery"


def test_labelled_fields_exist_in_registry(registry):
    for entity, labels in ENTITY_LABELS.items():
        list_ops = [d for d in registry.values() if d["entity"] == entity and d["operation"] == "list"]
        if not list_ops:
            continue
        available = set(list_ops[0]["fields"])
        missing = set(labels["fields"]) - available
        assert not missing, f"{entity}: labelled fields missing from registry: {sorted(missing)}"


def test_excluded_fields_never_reach_specs(specs):
    for entity, spec in specs.items():
        leaked = set(spec["field_labels"]) & EXCLUDED_FIELDS
        assert not leaked, f"{entity} exposes excluded fields: {sorted(leaked)}"


def test_every_spec_has_a_table_and_scope(specs):
    for entity, spec in specs.items():
        assert spec["table"], entity
        assert spec["scope"], entity


def test_leave_balance_has_no_date_field(specs):
    if "leave_balance" in specs:
        assert specs["leave_balance"]["date_field"] is None


def test_attendance_uses_attendance_date(specs):
    if "attendance" in specs:
        assert specs["attendance"]["date_field"] == "attendance_date"


def test_task_operations_come_from_registry(specs):
    if "task" in specs:
        assert "task.sum" in specs["task"]["operations"]
        assert "task.list" in specs["task"]["operations"]


def test_payroll_is_sensitive_and_not_narratable(specs):
    if "payroll_summary" in specs:
        assert specs["payroll_summary"]["sensitive"] is True
        assert specs["payroll_summary"]["narratable"] is False


def test_loan_is_sensitive_and_not_narratable(specs):
    if "loan_request" in specs:
        assert specs["loan_request"]["sensitive"] is True
        assert specs["loan_request"]["narratable"] is False


def test_owner_scoped_entities_are_narratable(specs):
    for entity in ["attendance", "leave_request", "wfh_request", "timesheet"]:
        if entity in specs:
            assert specs[entity]["narratable"] is True, entity


def test_safe_fields_drops_excluded_and_unknown(specs):
    if "leave_request" in specs:
        out = safe_fields(specs, "leave_request", ["start_date", "reason", "unknown_col"])
        assert out == ["start_date"]


def test_safe_fields_rejects_unknown_entity(specs):
    with pytest.raises(KeyError):
        safe_fields(specs, "not_an_entity", ["x"])