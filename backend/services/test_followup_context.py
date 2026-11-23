from backend.services.followup_context import apply_context_period

CONTEXT = {"operation_id": "attendance.list", "start_date": "2026-10-20", "end_date": "2026-10-20"}
PERIOD = {"start_date": "2026-11-01", "end_date": "2026-11-23"}


def test_short_followup_reuses_stored_period():
    period, reused = apply_context_period("clock out time?", PERIOD, CONTEXT, False)
    assert reused
    assert period["start_date"] == "2026-10-20"


def test_followup_keeps_string_type():
    period, _ = apply_context_period("clock out time?", PERIOD, CONTEXT, False)
    assert isinstance(period["start_date"], str)


def test_question_with_its_own_date_is_not_changed():
    period, reused = apply_context_period("clock out time on 5 October?", PERIOD, CONTEXT, True)
    assert not reused
    assert period == PERIOD


def test_long_selfcontained_question_is_not_changed():
    question = "How many leave requests did I have in the whole of this financial year so far?"
    period, reused = apply_context_period(question, PERIOD, CONTEXT, False)
    assert not reused


def test_no_context_means_no_change():
    period, reused = apply_context_period("clock out time?", PERIOD, None, False)
    assert not reused


def test_works_for_any_entity():
    leave_context = {"operation_id": "leave_request.list",
                     "start_date": "2026-10-01", "end_date": "2026-10-31"}
    period, reused = apply_context_period("how many approved?", PERIOD, leave_context, False)
    assert reused
    assert period["end_date"] == "2026-10-31"