from backend.services.fact_verifier import verify_against_facts as v

LATE = {"shape": "count", "entity": "attendance", "unit": "days", "unit_singular": "day",
        "period_text": "in October 2026", "filters": {"status": "late"},
        "count": 2, "found": True, "status": "late"}
TASK = {"entity": "task", "unit": "tasks", "unit_singular": "task",
        "period_text": "in October 2026", "count": 1, "found": True}
TIMESHEET = {"entity": "timesheet", "unit": "timesheets", "unit_singular": "timesheet",
             "period_text": "in October 2026", "count": 1, "found": True,
             "filters": {"status": "submitted"}, "status": "submitted"}
OVERTIME = {"entity": "attendance", "unit": "days", "unit_singular": "day",
            "period_text": "in October 2026", "measure": "overtime",
            "hours": 1, "minutes": 20, "found": True}
ZERO_ABSENT = {"entity": "attendance", "unit": "days", "unit_singular": "day",
               "period_text": "in October 2026", "filters": {"status": "absent"},
               "count": 0, "found": False, "status": "absent"}
GROUPS = {"entity": "attendance", "unit": "days", "unit_singular": "day",
          "period_text": "in October 2026", "found": True,
          "groups": [{"label": "late", "count": 2}, {"label": "present", "count": 14}]}
LEAVE_TYPES = {"entity": "leave type", "unit": "leave types", "unit_singular": "leave type",
               "period_text": "on record", "found": True,
               "rows": [{"name": "Casual Leave"}, {"name": "Sick Leave"}]}


def test_correct_count_passes():
    assert v("You were late for 2 days in October 2026.", LATE) is None
    assert v("You have 2 late days in October 2026.", LATE) is None


def test_wrong_number_fails():
    assert v("You were late for 3 days in October 2026.", LATE) == "number_not_in_facts"


def test_wrong_unit_fails():
    one = dict(LATE, count=1)
    assert v("You were late for 1 days in October 2026.", one) == "unit_plural_for_one"
    assert v("You were late for 2 day in October 2026.", LATE) == "unit_singular_for_many"


def test_wrong_period_fails():
    assert v("You were late for 2 days in November 2026.", LATE) == "unsupported_word:november"


def test_unsupported_status_fails():
    assert v("You were late for 2 days and absent once in October 2026.", LATE) is not None


def test_first_person_fails():
    assert v("I was late for 2 days in October 2026.", LATE) == "first_person_I"


def test_verb_agreement():
    assert v("1 task was found in October 2026.", TASK) is None
    assert v("1 task were found in October 2026.", TASK) == "verb_plural_for_one"


def test_timesheet_singular_with_status_passes():
    assert v("You have 1 submitted timesheet in October 2026.", TIMESHEET) is None


def test_time_total_uses_hours_not_days():
    assert v("In October 2026, you worked 1 hour and 20 minutes of overtime.", OVERTIME) is None
    assert v("In October 2026, you worked 1 day and 20 minutes of overtime.", OVERTIME) == "day_word_for_time_total"


def test_zero_count_passes_and_bare_zero_fails():
    assert v("No absent days were found in October 2026.", ZERO_ABSENT) is None
    assert v("0 absent days were found in October 2026.", ZERO_ABSENT) == "zero_digit"


def test_negating_a_positive_status_fails():
    assert v("No late days were found in October 2026.", GROUPS) == "negated_positive_status"


def test_group_breakdown_passes():
    assert v("In October 2026, 14 days were present and 2 days were late.", GROUPS) is None


def test_invented_name_fails():
    assert v("They are Casual Leave and Sickle Leave.", LEAVE_TYPES) == "unsupported_word:sickle"
    assert v("They are Casual Leave and Sick Leave.", LEAVE_TYPES) is None


def test_amount_formats_match():
    payroll = {"entity": "payroll", "shape": "amount", "period_text": "in September 2026",
               "metrics": [{"field": "net_amount", "label": "net amount",
                            "amounts": [{"value": "64680.00", "currency": "INR"}]}]}
    assert v("Your net amount in September 2026 was INR 64,680.00.", payroll) is None
    assert v("Your net amount in September 2026 was 64680.00 INR.", payroll) is None
    assert v("Your net amount in September 2026 was INR 64,681.00.", payroll) == "number_not_in_facts"

def test_spelled_number_checked_against_facts():
    assert v("Four leave types are available on record.", LEAVE_TYPES) == "spelled_number_not_in_facts"