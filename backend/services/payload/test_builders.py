from datetime import date
import pytest
from backend.services.payload.builders import (
    PayloadError, build_count, build_group_by, build_list_short,
    build_single, build_summary, build_sum,
)
from backend.services.payload.fit import fit_payload

START, END = date(2026, 11, 9), date(2026, 11, 15)
ATT = {
    "label": "attendance", "unit": "days", "narratable": True,
    "field_labels": {"attendance_date": "date", "status": "status", "worked_minutes": "worked time"},
}
TASK = {
    "label": "task", "unit": "tasks", "narratable": True,
    "field_labels": {"title": "title", "status": "status", "performance_score": "performance score"},
}
LOAN = {"label": "loan", "unit": "loans", "narratable": False, "field_labels": {}}


class CharTokenizer:
    def encode(self, text):
        return list(text)


def test_count_payload():
    p = build_count(ATT, 1, START, END, {"status": "absent"})
    assert p["result"] == {"count": 1}
    assert p["filters"] == {"status": "absent"}
    assert p["period"]["label"] == "9 Nov 2026 to 15 Nov 2026"


def test_sum_converts_minutes_to_hours_and_minutes():
    p = build_sum(ATT, "worked_minutes", 2670, START, END)
    assert p["result"]["hours"] == 44
    assert p["result"]["minutes"] == 30


def test_group_by_labels_statuses():
    rows = [{"group_value": "half_day", "record_count": 2}]
    p = build_group_by(ATT, rows, START, END)
    assert p["result"]["groups"] == [{"label": "half day", "count": 2}]


def test_list_is_capped_and_marked_truncated():
    rows = [{"attendance_date": f"2026-11-{i:02d}", "status": "present"} for i in range(1, 13)]
    p = build_list_short(ATT, "attendance", rows, 12, START, END, role="employee")
    assert len(p["rows"]) == 5
    assert p["truncated"] is True


def test_list_drops_fields_not_in_spec():
    rows = [{"status": "present", "reason": "private note"}]
    p = build_list_short(ATT, "attendance", rows, 1, START, END, role="employee")
    assert "reason" not in p["rows"][0]


def test_performance_score_hidden_from_employee_shown_to_admin():
    rows = [{"title": "Report", "performance_score": 4}]
    employee = build_list_short(TASK, "task", rows, 1, START, END, role="employee")
    admin = build_list_short(TASK, "task", rows, 1, START, END, role="admin")
    assert "performance_score" not in employee["rows"][0]
    assert "performance_score" in admin["rows"][0]


def test_single_not_found():
    p = build_single(ATT, "attendance", None, date(2026, 11, 3), role="employee")
    assert p["found"] is False
    assert p["result"] == {}


def test_summary_keeps_three_months_at_most():
    months = [{"month": f"M{i}", "present": 1} for i in range(5)]
    p = build_summary(ATT, {"present": 5}, months, START, END)
    assert len(p["by_month"]) == 3


def test_non_narratable_entity_is_refused():
    with pytest.raises(PayloadError):
        build_count(LOAN, 2, START, END)


def test_fit_drops_rows_to_fit_budget():
    rows = [{"attendance_date": f"2026-11-{i:02d}", "status": "present"} for i in range(1, 6)]
    p = build_list_short(ATT, "attendance", rows, 5, START, END, role="employee")
    fitted = fit_payload(p, CharTokenizer(), max_tokens=len(str(p)) - 100)
    assert "rows" not in fitted
    assert fitted["truncated"] is True