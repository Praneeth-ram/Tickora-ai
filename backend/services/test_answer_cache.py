import time
import pytest
from fastapi import HTTPException
from backend.services import answer_cache as cache
from backend.main import _build_answer_cache_key
from backend.security.access_policy import (
    Actor,
    set_actor,
    reset_actor,
    set_subject,
    reset_subject,
)

def test_plan_is_shared_across_users_by_key():
    key = cache.plan_key("show my leave balance", "2026-11-14", "fp1")
    cache.set_plan(key, {"operation_id": "leave_balance.list", "filters": {}}, 60)
    assert cache.get_plan(key) == {"operation_id": "leave_balance.list", "filters": {}}

def test_answer_key_includes_employee_and_role():
    a = cache.answer_key(11, "employee", "holidays", "2026-11-14")
    b = cache.answer_key(12, "employee", "holidays", "2026-11-14")
    c = cache.answer_key(11, "admin", "holidays", "2026-11-14")
    assert a != b
    assert a != c

def test_answer_is_not_returned_to_another_employee():
    key_a = cache.answer_key(11, "employee", "leave balance", "2026-11-14")
    cache.set_answer(key_a, {"answer": "You have 37 days."}, 60)
    key_b = cache.answer_key(12, "employee", "leave balance", "2026-11-14")
    assert cache.get_answer(key_b) is None

def test_answer_expires():
    key = cache.answer_key(11, "employee", "x", "2026-11-14")
    cache.set_answer(key, {"answer": "a"}, 1)
    assert cache.get_answer(key) is not None
    time.sleep(1.1)
    assert cache.get_answer(key) is None

def test_clear_answers_for_removes_only_that_employee():
    key_a = cache.answer_key(21, "employee", "q", "2026-11-14")
    key_b = cache.answer_key(22, "employee", "q", "2026-11-14")
    cache.set_answer(key_a, {"answer": "a"}, 60)
    cache.set_answer(key_b, {"answer": "b"}, 60)
    cache.clear_answers_for(21)
    assert cache.get_answer(key_a) is None
    assert cache.get_answer(key_b) is not None

def test_returned_values_are_copies():
    key = cache.plan_key("copy test", "2026-11-14", "fp1")
    cache.set_plan(key, {"operation_id": "x", "filters": {}}, 60)
    got = cache.get_plan(key)
    got["operation_id"] = "changed"
    assert cache.get_plan(key)["operation_id"] == "x"

def test_same_question_with_different_topic_has_different_key():
    a = cache.answer_key(11, "employee", "what about november?", "2026-11-14", "attendance")
    b = cache.answer_key(11, "employee", "what about november?", "2026-11-14", "leave balance")
    assert a != b

def test_answer_cache_key_changes_when_employee_role_changes():
    employee = Actor(
        employee_id=11,
        organization_id=1,
        department_id=2,
        role="employee",
        employee_code="EMP011",
    )

    admin = Actor(
        employee_id=11,
        organization_id=1,
        department_id=2,
        role="admin",
        employee_code="EMP011",
    )

    employee_token = set_actor(employee)
    try:
        employee_key = _build_answer_cache_key(
            11, "show attendance", "2026-11-24", ""
        )
    finally:
        reset_actor(employee_token)

    admin_token = set_actor(admin)
    try:
        admin_key = _build_answer_cache_key(
            11, "show attendance", "2026-11-24", ""
        )
    finally:
        reset_actor(admin_token)

    assert employee_key != admin_key


def test_answer_cache_key_changes_when_department_changes():
    actor_a = Actor(11, 1, 2, "admin", "EMP011")
    actor_b = Actor(11, 1, 3, "admin", "EMP011")

    token_a = set_actor(actor_a)
    try:
        key_a = _build_answer_cache_key(
            11, "show attendance", "2026-11-24", ""
        )
    finally:
        reset_actor(token_a)

    token_b = set_actor(actor_b)
    try:
        key_b = _build_answer_cache_key(
            11, "show attendance", "2026-11-24", ""
        )
    finally:
        reset_actor(token_b)

    assert key_a != key_b


def test_answer_cache_key_changes_when_resolved_subject_changes():
    actor = Actor(11, 1, 2, "admin", "EMP011")

    actor_token = set_actor(actor)
    try:
        subject_token_a = set_subject(21)
        try:
            key_a = _build_answer_cache_key(
                11, "show attendance", "2026-11-24", ""
            )
        finally:
            reset_subject(subject_token_a)

        subject_token_b = set_subject(22)
        try:
            key_b = _build_answer_cache_key(
                11, "show attendance", "2026-11-24", ""
            )
        finally:
            reset_subject(subject_token_b)
    finally:
        reset_actor(actor_token)

    assert key_a != key_b


def test_answer_cache_key_rejects_missing_actor():
    with pytest.raises(HTTPException):
        _build_answer_cache_key(
            11, "show attendance", "2026-11-24", ""
        )