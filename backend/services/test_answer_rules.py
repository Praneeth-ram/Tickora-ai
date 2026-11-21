from backend.services.answer_writer import passes_answer_check, ANSWER_RULES
from backend.services.payload.answer_payload import period_text


def test_comma_before_year_is_rejected():
    assert not passes_answer_check(
        "You had 14 present days in October, 2026.",
        {"found": True, "count": 14, "status": "present"},
    )


def test_correct_count_passes():
    assert passes_answer_check(
        "You had 14 present days in October 2026.",
        {
            "found": True,
            "count": 14,
            "status": "present",
            "period_text": "October 2026",
        },
    )


def test_repeated_unit_word_is_rejected():
    assert not passes_answer_check(
        "You had 2 late days in October, half day days.",
        {
            "found": True,
            "count": 2,
            "status": "late",
            "period_text": "October 2026",
        },
    )


def test_unit_singular_and_plural_must_match():
    facts = {"found": True, "hours": 1, "minutes": 42, "measure": "worked time"}
    assert not passes_answer_check("You worked 1 hours and 42 minutes.", facts)
    assert passes_answer_check("You worked 1 hour and 42 minutes.", facts)


def test_duplicate_month_and_month_comma_year_are_rejected():
    facts = {
        "found": True,
        "count": 14,
        "period_text": "October 2026",
    }
    assert not passes_answer_check(
        "You had 14 days in October, October 2026.",
        facts,
    )
    assert not passes_answer_check(
        "You had 14 days in October, for the year 2026.",
        facts,
    )


def test_relative_and_unmatched_months_are_rejected():
    facts = {
        "found": True,
        "count": 2,
        "status": "late",
        "period_text": "November 2026",
    }
    assert not passes_answer_check(
        "You had 2 late days this November 2026.",
        facts,
    )
    assert not passes_answer_check(
        "You had 2 late days in October 2026.",
        facts,
    )
    assert not passes_answer_check(
        "You had 2 late days in the specified period.",
        facts,
    )


def test_negated_status_is_rejected():
    assert not passes_answer_check(
        "You had no late days in October.",
        {"found": True, "count": 2, "status": "late"},
    )


def test_vague_period_is_rejected_by_rule_only():
    # Enforced by the prompt (rule 21), not by passes_answer_check.
    assert "the specified period" in ANSWER_RULES.lower()


def test_per_status_routes_to_template_without_groups():
    from backend.agents import nodes
    from unittest.mock import patch

    result = {
        "answer": "You have 1 leave request.",
        "message": "You have 1 leave request.",
        "show_table": False,
        "data": {"count": 1},
    }
    with patch.object(nodes, "settings") as settings:
        settings.llm_narration_enabled = True
        with patch.object(nodes, "write_answer") as write_answer:
            out = nodes._route_answer(
                "How many leave requests per status?",
                result,
                {"operation_id": "leave_request.count", "filters": {}},
                {"start_date": None, "end_date": None},
            )
            write_answer.assert_not_called()
        assert out["answer"] == nodes.LEAVE_STATUS_BREAKDOWN_MESSAGE
        assert out["message"] == nodes.LEAVE_STATUS_BREAKDOWN_MESSAGE


def test_overtime_template_deduplicates_month_and_pluralizes_units():
    from backend.services.llm_chat_service import _hours_sentence, sum_response

    rows = [{"overtime_minutes": 60}]
    span = "in October, October 2026"
    assert _hours_sentence(rows, span, True) == (
        "Your total overtime in October 2026 was 1 hour and 0 minutes."
    )
    assert sum_response("overtime_minutes", 60, span) == (
        "You recorded 1 hour and 0 minutes of overtime in October 2026."
    )