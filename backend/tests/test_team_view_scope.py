# backend/tests/test_team_view_scope.py
from datetime import date
from backend.services.dynamic_query_service import execute_team_summary, TEAM_SUMMARY_LIMIT
from .conftest import EMP001, EMP002


def _actor(tup):
    from backend.security.access_policy import Actor
    employee_id, org_id, dept_id, role = tup
    return Actor(employee_id, org_id, dept_id, role)


def test_admin_team_view_is_department_scoped_no_department_column():
    actor = _actor(EMP002)
    result = execute_team_summary(actor=actor, start=date(2026, 10, 1), end=date(2026, 10, 31))
    rows = result["rows"]
    assert rows, "expected department 2 to have attendance in October"
    for row in rows:
        assert "department_id" in row  # raw row always has it
    # The response-shaping layer in llm_chat_service.team_attendance_result
    # is what drops the department column for non-super-admins -- check that
    # layer directly too:
    from backend.services.llm_chat_service import team_attendance_result
    shaped = team_attendance_result("Show my team's attendance for October.", actor,
                                     date(2026, 10, 1), date(2026, 10, 31))
    for item in shaped["data"]:
        assert "department" not in item


def test_super_admin_team_view_includes_department_column():
    actor = _actor(EMP001)
    from backend.services.llm_chat_service import team_attendance_result
    shaped = team_attendance_result("Show attendance for everyone for October.", actor,
                                     date(2026, 10, 1), date(2026, 10, 31))
    assert shaped["data"], "expected organization-wide rows"
    assert all("department" in item for item in shaped["data"])
    departments_seen = {item["department"] for item in shaped["data"]}
    assert len(departments_seen) > 1  # proves it spans more than one department


def test_team_view_caps_at_fifty(monkeypatch):
    actor = _actor(EMP001)
    fake_rows = [
        {"full_name": f"Person {i}", "employee_code": f"EMP{i:03d}",
         "department_id": 1, "present": 1, "late": 0, "absent": 0, "half_day": 0}
        for i in range(55)
    ]
    import backend.services.llm_chat_service as mod
    monkeypatch.setattr(mod, "execute_team_summary", lambda **kw: {"rows": fake_rows})
    result = mod.team_attendance_result("Show everyone's attendance for October.", actor,
                                          date(2026, 10, 1), date(2026, 10, 31))
    assert len(result["data"]) == TEAM_SUMMARY_LIMIT
    assert "first 50" in result["answer"]