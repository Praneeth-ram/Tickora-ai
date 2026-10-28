"""Leave balance routing and answers, using the employee's reported numbers.

The database is replaced with fakes, so these run without PostgreSQL.
"""
import os
from datetime import date
import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://u:p@localhost:5432/x")

from backend.services import leave_balance_answer as lba  # noqa: E402
from backend.services import llm_chat_service as svc  # noqa: E402

TODAY = date(2026, 10, 26)
LEAVE_TYPES = [
    {"id": 1, "code": "CASUAL", "name": "Casual Leave", "is_paid": True},
    {"id": 2, "code": "SICK", "name": "Sick Leave", "is_paid": True},
    {"id": 3, "code": "EARNED", "name": "Earned Leave", "is_paid": True},
    {"id": 4, "code": "UNPAID", "name": "Unpaid Leave", "is_paid": False},
]
BALANCES = [
    {"leave_type_id": 2, "year": 2026, "allocated_days": 10, "used_days": 3, "pending_days": 1},
    {"leave_type_id": 3, "year": 2026, "allocated_days": 15, "used_days": 5, "pending_days": 0},
    {"leave_type_id": 4, "year": 2026, "allocated_days": 0, "used_days": 0, "pending_days": 0},
    {"leave_type_id": 1, "year": 2026, "allocated_days": 12, "used_days": 2, "pending_days": 0},
]


class FakeDB:
    def __init__(self):
        self.calls = []

    def __call__(self, plan, *, employee_id, limit=50, **_):
        self.calls.append((plan, employee_id))
        op = plan["operation_id"]
        # Accept both "leave_type.list" (real) and "leave_types.list" (legacy test alias)
        if op in ("leave_type.list", "leave_types.list"):
            data = list(LEAVE_TYPES)
        elif op == "leave_balance.list":
            data = [dict(r) for r in BALANCES]
            f = plan["filters"]
            data = [r for r in data if r["year"] == f.get("year", r["year"])]
            if "leave_type_id" in f:
                data = [r for r in data if r["leave_type_id"] == f["leave_type_id"]]
        else:
            raise AssertionError(f"unexpected operation {op!r}")
        return {"operation_id": op, "entity": op.split(".")[0], "operation": "list", "data": data, "limit": limit}


@pytest.fixture
def db(monkeypatch):
    fake = FakeDB()
    monkeypatch.setattr(svc, "execute_query_plan", fake)
    monkeypatch.setattr(svc, "get_current_date", lambda: TODAY)
    # The model must not be consulted for balance questions.
    def no_model(_):
        raise AssertionError("model should not be called for leave balance questions")
    monkeypatch.setattr(svc, "get_query_plan", no_model)
    return fake


# ---------------------------------------------------------------------------
# Routing detection: is_leave_balance_question
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("question", [
    # Original cases
    "what is my allocated days for sick leave",
    "what is my allocated days for sick leave in 2026",
    "how many pending leave days i have?",
    "what is my total allocated leave days",
    "what is my leave balance",
    "how many casual leave days did i use",
    # Extended metric synonyms
    "what is my leave entitlement for this year",
    "how many sick leave days are remaining",
    "how many earned leave days are available",
    "show me my leave quota",
    "what is my leave balance left",
    "how much leave have i accrued",
    "do i have any carryover leave",
    # Named leave type without explicit metric word (Rule 3)
    "how many sick days do i have",
    "how many casual days are left",
    "how many maternity leave days do i have",
    "how many comp off days remain",
    # Grammar variations / naturalness
    "what are my allocated days for sick leave?",
    "tell me my leave balance",
    "show leave balance",
    "remaining leave days this year",
])
def test_balance_questions_are_detected(question):
    assert lba.is_leave_balance_question(question), f"Expected balance: {question!r}"


@pytest.mark.parametrize("question", [
    # Request workflow — must NOT be classified as balance
    "how many pending leave requests do i have",
    "show my leave request status",
    "how many wfh requests are pending",
    "i want to apply for leave",
    "my leave was cancelled",
    "cancel my sick leave",
    # Other domains
    "what are the holidays in february",
    "show my attendance for october",
    "clock in time today",
    "how many days was i late this month",
    "timesheet status",
])
def test_request_and_other_questions_are_not_balance(question):
    assert not lba.is_leave_balance_question(question), f"Expected NOT balance: {question!r}"


# ---------------------------------------------------------------------------
# End-to-end: sentence generation from fake DB data
# ---------------------------------------------------------------------------

def test_sick_leave_allocated_is_one_sentence(db):
    result = svc.run_llm_chat("what is my allocated days for sick leave", employee_id=7)
    assert result["answer"] == "You have 10 allocated Sick Leave days in 2026."
    assert result["show_table"] is False
    assert db.calls[0][0]["operation_id"] == "leave_type.list"


def test_sick_leave_allocated_with_year(db):
    result = svc.run_llm_chat("what is my allocated days for sick leave in 2026", employee_id=7)
    assert result["answer"] == "You have 10 allocated Sick Leave days in 2026."


def test_pending_days_across_types(db):
    result = svc.run_llm_chat("how many pending leave days i have?", employee_id=7)
    assert result["answer"] == "You have 1 pending leave days in 2026 (1 Sick Leave)."


def test_total_allocated_across_types(db):
    result = svc.run_llm_chat("what is my total allocated leave days", employee_id=7)
    assert "37" in result["answer"]
    assert "allocated" in result["answer"]


def test_full_balance_lists_each_type_with_names(db):
    result = svc.run_llm_chat("what is my leave balance", employee_id=7)
    assert "Casual Leave" in result["answer"]
    assert "Sick Leave" in result["answer"]


def test_used_days_for_one_type(db):
    result = svc.run_llm_chat("how many casual leave days did i use", employee_id=7)
    assert result["answer"] == "You have used 2 Casual Leave days in 2026."


def test_year_with_no_balance_is_a_clear_sentence(db):
    result = svc.run_llm_chat("what is my allocated days for sick leave in 2024", employee_id=7)
    assert result["answer"] == "I couldn't find a Sick Leave balance for 2024."


def test_employee_id_is_always_the_token_employee(db):
    svc.run_llm_chat("what is my leave balance", employee_id=42)
    assert all(emp_id == 42 for _, emp_id in db.calls)


def test_sick_days_without_metric_word_is_balance(db):
    """'how many sick days do i have' — no metric word, but has leave type + days."""
    result = svc.run_llm_chat("how many sick days do i have", employee_id=7)
    # Should return balance, not a leave-request count
    assert result["intent"] == "leave_balance"
    assert "Sick Leave" in result["answer"]


def test_remaining_sick_leave_balance(db):
    result = svc.run_llm_chat("how many sick leave days are remaining", employee_id=7)
    assert result["intent"] == "leave_balance"
    # sick: 10 allocated - 3 used - 1 pending = 6 remaining
    assert "6" in result["answer"]


def test_leave_entitlement_synonym(db):
    result = svc.run_llm_chat("what is my leave entitlement for this year", employee_id=7)
    assert result["intent"] == "leave_balance"


def test_pending_leave_requests_not_rerouted_to_balance(db):
    """'pending leave requests' must NOT be treated as a balance question."""
    # is_leave_balance_question should return False; this verifies the guard
    assert not lba.is_leave_balance_question("how many pending leave requests do i have")


# ---------------------------------------------------------------------------
# Pure module checks
# ---------------------------------------------------------------------------

def test_leave_type_match_is_longest_name_first():
    assert lba.match_leave_type("sick leave", LEAVE_TYPES)["id"] == 2
    assert lba.match_leave_type("unpaid days", LEAVE_TYPES)["id"] == 4


def test_fractional_days_are_formatted_without_trailing_zeros():
    assert lba.format_days(10.0) == "10"
    assert lba.format_days(10.5) == "10.5"
    assert lba.format_days(0) == "0"


def test_detect_metric_priority():
    """pending is highest priority even when other metric words also appear."""
    assert lba.detect_metric("pending allocated leave") == "pending"
    assert lba.detect_metric("how many sick leave days did i use") == "used"
    assert lba.detect_metric("how many sick leave days are left") == "remaining"
    assert lba.detect_metric("what is my leave entitlement") == "allocated"


def test_match_leave_type_compoff(tmp_path):
    types = [{"id": 5, "code": "COMP", "name": "Comp Off", "is_paid": False}]
    assert lba.match_leave_type("how many comp off days do i have", types)["id"] == 5


def test_enrich_rows_adds_leave_type_name():
    rows = [{"leave_type_id": 1, "year": 2026, "allocated_days": 12, "used_days": 2, "pending_days": 0}]
    enriched = lba.enrich_rows(rows, LEAVE_TYPES)
    assert enriched[0]["leave_type"] == "Casual Leave"
    assert enriched[0]["year"] == "2026"