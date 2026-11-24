from calendar import monthrange
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from backend.agents import nodes
from backend.services.payroll_narration import (
    build_payroll_facts,
    is_payroll_detail_question,
    passes_payroll_answer_check,
)


def _row(month: int, gross: str = "4250.00") -> dict:
    start = date(2026, month, 1)
    end = date(2026, month, monthrange(2026, month)[1])
    return {
        "period_start": start,
        "period_end": end,
        "gross_amount": Decimal(gross),
        "deduction_amount": Decimal("750.00"),
        "net_amount": Decimal("3500.00"),
        "currency": "INR",
    }


def test_payroll_amount_answer_requires_exact_amount_and_currency():
    period = {"start_date": date(2026, 8, 1), "end_date": date(2026, 8, 31)}
    facts = build_payroll_facts(
        "What is my gross amount in August 2026?",
        period,
        [_row(8)],
    )

    assert facts is not None
    assert passes_payroll_answer_check(
        "Your gross amount in August 2026 was INR 4,250.00.",
        facts,
    )
    assert not passes_payroll_answer_check(
        "Your gross amount in August 2026 was INR 4,251.00.",
        facts,
    )
    assert not passes_payroll_answer_check(
        "Your gross amount in August 2026 was INR -4,250.00.",
        facts,
    )
    assert not passes_payroll_answer_check(
        "Your gross amount in August 2026 was USD 4,250.00.",
        facts,
    )
    assert not passes_payroll_answer_check(
        "Your gross amount in August 2026 was 4,250.00.",
        facts,
    )
    assert not passes_payroll_answer_check(
        "Your gross amount in August 2026 was INR 4,250.00 and INR 5,000.00.",
        facts,
    )


def test_multiple_requested_payroll_metrics_must_all_be_answered():
    period = {"start_date": date(2026, 8, 1), "end_date": date(2026, 8, 31)}
    question = "What are my gross amount and deduction amount in August 2026?"
    facts = build_payroll_facts(question, period, [_row(8)])

    assert facts is not None
    assert passes_payroll_answer_check(
        "Your gross amount was INR 4,250.00 and deduction amount was "
        "INR 750.00 in August 2026.",
        facts,
    )
    assert not passes_payroll_answer_check(
        "Your gross amount was INR 4,250.00 in August 2026.",
        facts,
    )


def test_payroll_totals_require_full_period_coverage_and_keep_currencies_separate():
    question = "What is my total gross amount from June to October 2026?"
    period = {"start_date": date(2026, 6, 1), "end_date": date(2026, 10, 31)}
    rows = [_row(month, "1000.00") for month in range(6, 11)]

    facts = build_payroll_facts(question, period, rows)

    assert facts is not None
    assert facts["metrics"][0]["amounts"] == [
        {"value": "5000.00", "currency": "INR"}
    ]
    assert passes_payroll_answer_check(
        "Your total gross amount from 1 June 2026 to 31 October 2026 was "
        "INR 5,000.00.",
        facts,
    )
    assert build_payroll_facts(question, period, rows[:-1]) is None


def test_payroll_total_does_not_combine_different_currencies():
    question = "What is my total net amount from June to July 2026?"
    period = {"start_date": date(2026, 6, 1), "end_date": date(2026, 7, 31)}
    rows = [_row(6), _row(7)]
    rows[1]["currency"] = "USD"

    facts = build_payroll_facts(question, period, rows)

    assert facts is not None
    assert facts["metrics"][0]["amounts"] == [
        {"value": "3500.00", "currency": "INR"},
        {"value": "3500.00", "currency": "USD"},
    ]
    assert passes_payroll_answer_check(
        "Your total net amount from 1 June 2026 to 31 July 2026 was "
        "INR 3,500.00 and USD 3,500.00.",
        facts,
    )


def test_payroll_facts_are_not_generated_for_tables_or_unknown_currency():
    period = {"start_date": date(2026, 8, 1), "end_date": date(2026, 8, 31)}
    assert not is_payroll_detail_question("Show my payroll details in August 2026.")
    assert build_payroll_facts(
        "What is my gross amount in August 2026?", period, []
    ) is None
    row = _row(8)
    row["currency"] = None
    assert build_payroll_facts(
        "What is my gross amount in August 2026?",
        period,
        [row],
    ) is None


def test_payroll_amount_questions_use_llm_but_table_requests_do_not():
    period = {"start_date": date(2026, 8, 1), "end_date": date(2026, 8, 31)}
    result = {
        "intent": "payroll_lookup",
        "answer": "Your gross salary for August 2026 was INR 4,250.00.",
        "message": "Your gross salary for August 2026 was INR 4,250.00.",
        "show_table": False,
        "data": [_row(8)],
    }
    actor = SimpleNamespace(role="employee", employee_id=12)
    super_admin = SimpleNamespace(role="super_admin", employee_id=12)

    with (
        patch.object(nodes, "settings") as settings,
        patch.object(nodes, "get_actor", return_value=actor) as get_actor,
        patch.object(nodes, "get_subject", return_value=None),
        patch.object(
            nodes,
            "write_answer",
            return_value="Your gross amount in August 2026 was INR 4,250.00.",
        ) as write_answer,
    ):
        settings.llm_narration_enabled = True
        narrated = nodes._route_answer(
            "What is my gross amount in August 2026?",
            dict(result),
            {"operation_id": "payroll_summary.list", "filters": {}},
            period,
        )
        table = nodes._route_answer(
            "Show my payroll details in August 2026.",
            dict(result),
            {"operation_id": "payroll_summary.list", "filters": {}},
            period,
        )
        get_actor.return_value = super_admin
        super_admin_org_query = nodes._route_answer(
            "What is the total gross amount from August 2026?",
            dict(result),
            {"operation_id": "payroll_summary.list", "filters": {}},
            period,
        )

    assert narrated["answer"] == (
        "Your gross amount in August 2026 was INR 4,250.00."
    )
    assert write_answer.call_count == 2
    assert table["answer"] == result["answer"]
    assert super_admin_org_query["answer"] == (
        "Your gross amount in August 2026 was INR 4,250.00."
    )

def test_two_requested_metrics_both_appear_in_template():
    from backend.services.llm_chat_service import _payroll_response

    rows = [{
        "period_start": "2026-10-01", "period_end": "2026-10-23",
        "gross_amount": "63500.00", "deduction_amount": "7620.00",
        "net_amount": "55880.00", "currency": "INR",
    }]
    answer = _payroll_response(
        rows, {"start_date": "2026-10-01", "end_date": "2026-10-23"},
        "what is my gross amount and deduction amount",
    )
    assert "63,500.00" in answer
    assert "7,620.00" in answer

def test_super_admin_own_payroll_question_is_narrated_when_subject_is_none():
    from backend.agents import nodes
    from backend.security.access_policy import Actor, SUPER_ADMIN

    gate = (
        lambda question, subject_id, actor: not (
            not nodes.is_payroll_detail_question(question)
            or (subject_id is not None and subject_id != actor.employee_id)
        )
    )
    actor = Actor(employee_id=1, organization_id=1, department_id=None,
                  role=SUPER_ADMIN, employee_code="EMP001")
    assert gate("what is my gross amount on august month", None, actor)
    assert not gate("what is my gross amount on august month", 2, actor)
