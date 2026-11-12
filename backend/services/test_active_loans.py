from datetime import date

from backend.services.llm_chat_service import (
    _describe_loan_matches,
    _loan_value_filters,
    normalize_and_correct_plan,
)

CATALOG = {
    "status": ["Approved", "Pending"],
    "loan_status": ["Active", "Closed"],
    "mode": ["INSTALLMENT"],
}


def test_active_matches_stored_loan_status():
    plan = {"operation_id": "loan_request.count", "filters": {}}
    normalized, _ = normalize_and_correct_plan(
        plan, "How many loans are currently active?", date(2026, 11, 6), loan_values=CATALOG
    )
    assert normalized["filters"].get("loan_status") == "Active"


def test_approved_matches_stored_status_not_loan_status():
    plan = {"operation_id": "loan_request.list", "filters": {"loan_status": "approved"}}
    normalized, _ = normalize_and_correct_plan(
        plan, "which loan status has been approved?", date(2026, 11, 6), loan_values=CATALOG
    )
    assert normalized["filters"].get("status") == "Approved"
    assert "loan_status" not in normalized["filters"]


def test_ambiguous_value_is_not_applied():
    catalog = {"status": ["Active"], "loan_status": ["Active"], "mode": []}
    assert _loan_value_filters("show active loans", catalog) == {}


def test_sentence_names_filter_and_matching_loan():
    rows = [{"component": "Penalty Deduction", "status": "Approved", "loan_status": "Active"}]
    answer = _describe_loan_matches(rows, {"status": "Approved"})
    assert answer == "You have 1 loan with status Approved: Penalty Deduction (loan status Active)."


def test_sentence_when_no_loan_matches():
    assert _describe_loan_matches([], {"status": "Rejected"}) == (
        "You have no loans with status Rejected."
    )