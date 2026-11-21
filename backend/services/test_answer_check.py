from backend.services.answer_writer import passes_answer_check

LATE_FACTS = {"status": "late", "count": 2, "found": True}
WORKED_FACTS = {
    "measure": "worked time",
    "hours": 166,
    "minutes": 28,
    "found": True,
}


def test_status_count_without_negation_passes():
    assert passes_answer_check("You had 2 late days.", LATE_FACTS)


def test_negated_status_with_positive_count_fails():
    assert not passes_answer_check("You had no late days.", LATE_FACTS)


def test_negation_is_allowed_when_count_is_zero():
    facts = {"status": "late", "count": 0, "found": True}
    assert passes_answer_check("You had no late days.", facts)


def test_negated_group_status_with_positive_count_fails():
    facts = {"groups": [{"label": "absent", "count": 2}], "found": True}
    assert not passes_answer_check("You had no absences.", facts)


def test_parenthesised_minute_total_fails():
    assert not passes_answer_check(
        "166 hours and 28 minutes (9,988 minutes).", WORKED_FACTS
    )


def test_days_for_time_total_fails():
    assert not passes_answer_check("166 days and 28 hours.", WORKED_FACTS)


def test_comma_between_month_and_year_fails():
    facts = {"groups": [{"label": "present", "count": 14}], "found": True}
    assert not passes_answer_check("14 present days in October, 2026.", facts)


def test_correct_time_reply_passes():
    assert passes_answer_check("You worked 166 hours and 28 minutes.", WORKED_FACTS)
