from datetime import date
from decimal import Decimal

from backend.services.answer_builder import fmt_range
from backend.services.llm_chat_service import (
    count_response,
    format_timesheet_response,
    grouped_response,
    leave_type_response,
    sum_response,
)
from backend.services.request_answer_builder import request_answer


def test_count_answers_use_entity_names_and_singular_grammar():
    assert count_response("leave_request", 1, "approved", "in October 2026") == (
        "You have 1 approved leave request in October 2026."
    )
    assert count_response("holiday", 0, None, "in October 2026") == (
        "No holidays were found in October 2026."
    )


def test_sum_answers_humanize_metrics_and_decimal_results():
    assert sum_response("worked_minutes", Decimal("510"), "in October 2026") == (
        "You worked 8 hours and 30 minutes in October 2026."
    )
    assert sum_response("allocated_days", Decimal("1"), "in 2026") == (
        "Your total allocated leave in 2026 is 1 day."
    )


def test_grouped_answer_formats_statuses_as_a_summary():
    assert grouped_response(
        "attendance",
        [
            {"group_value": "PRESENT", "record_count": 4},
            {"group_value": "LATE", "record_count": 1},
        ],
        "status",
        "count",
        None,
        "in October 2026",
    ) == (
        "Your attendance breakdown by status in October 2026: "
        "present: 4 days, late: 1 day."
    )


def test_timesheet_answer_formats_periods_and_caps_long_lists():
    rows = [
        {
            "period_start": date(2026, 10, 5),
            "period_end": date(2026, 10, 11),
            "status": "APPROVED",
        }
    ]
    assert format_timesheet_response(rows) == (
        "Your timesheet:\n- 5 to 11 October 2026: Approved"
    )


def test_leave_types_are_named_without_exposing_database_ids():
    assert leave_type_response(
        [{"id": 3, "name": "Sick Leave", "is_paid": True}]
    ) == "There is 1 leave type: Sick Leave (paid)."


def test_request_answer_uses_concise_status_summary():
    answer = request_answer(
        "leave",
        [
            {"status": "approved", "start_date": date(2026, 10, 5), "end_date": date(2026, 10, 5)},
            {"status": "pending", "start_date": date(2026, 10, 12), "end_date": date(2026, 10, 12)},
        ],
        "show my leave requests",
        "in October 2026",
        False,
    )
    assert answer == "You have 2 leave requests in October 2026: 1 pending and 1 approved."


def test_single_request_summary_does_not_repeat_the_count():
    answer = request_answer(
        "leave",
        [{"status": "approved"}],
        "show my leave request",
        "",
        False,
    )
    assert answer == "Your leave request is approved."


def test_fractional_request_days_are_not_truncated():
    answer = request_answer(
        "leave",
        [{
            "status": "approved",
            "start_date": date(2026, 10, 5),
            "end_date": date(2026, 10, 5),
            "requested_days": 0.5,
        }],
        "how many days",
        "",
        False,
    )
    assert answer == "Your leave request for 5 October 2026 covers 0.5 days."


def test_date_range_helper_remains_human_readable():
    assert fmt_range(date(2026, 10, 1), date(2026, 10, 31)) == "October 2026"
