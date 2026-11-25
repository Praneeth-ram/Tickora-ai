
from backend.services.followup_context import (
    apply_context_period,
    inherit_fields,
)


PREVIOUS_ATTENDANCE_CONTEXT = {
    "operation_id": "attendance.list",
    "start_date": "2026-10-01",
    "end_date": "2026-10-31",
    "fields": ["clock in"],
}

CURRENT_PERIOD = {
    "start_date": "2026-11-01",
    "end_date": "2026-11-30",
}


def test_same_operation_followup_reuses_previous_period():
    period, reused = apply_context_period(
        question="What about clock-in?",
        period=CURRENT_PERIOD,
        last_context=PREVIOUS_ATTENDANCE_CONTEXT,
        has_explicit_date=False,
        operation_id="attendance.list",
    )

    assert reused is True
    assert period["start_date"] == "2026-10-01"
    assert period["end_date"] == "2026-10-31"


def test_different_operation_does_not_reuse_previous_period():
    period, reused = apply_context_period(
        question="What about my leave requests?",
        period=CURRENT_PERIOD,
        last_context=PREVIOUS_ATTENDANCE_CONTEXT,
        has_explicit_date=False,
        operation_id="leave_request.list",
    )

    assert reused is False
    assert period == CURRENT_PERIOD


def test_explicit_date_does_not_reuse_previous_period():
    period, reused = apply_context_period(
        question="What about November 2026?",
        period=CURRENT_PERIOD,
        last_context=PREVIOUS_ATTENDANCE_CONTEXT,
        has_explicit_date=True,
        operation_id="attendance.list",
    )

    assert reused is False
    assert period == CURRENT_PERIOD


def test_independent_question_does_not_reuse_previous_period():
    period, reused = apply_context_period(
        question="Please provide a detailed breakdown of my attendance",
        period=CURRENT_PERIOD,
        last_context=PREVIOUS_ATTENDANCE_CONTEXT,
        has_explicit_date=False,
        operation_id="attendance.list",
    )

    assert reused is False
    assert period == CURRENT_PERIOD


def test_same_operation_followup_inherits_previous_fields():
    fields = inherit_fields(
        question="And?",
        last_context=PREVIOUS_ATTENDANCE_CONTEXT,
        operation_id="attendance.list",
    )

    assert fields == ["clock in"]


def test_different_operation_does_not_inherit_previous_fields():
    fields = inherit_fields(
        question="And?",
        last_context=PREVIOUS_ATTENDANCE_CONTEXT,
        operation_id="leave_request.list",
    )

    assert fields == []
