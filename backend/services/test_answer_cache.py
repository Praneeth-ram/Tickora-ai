import time
from backend.services import answer_cache as cache

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