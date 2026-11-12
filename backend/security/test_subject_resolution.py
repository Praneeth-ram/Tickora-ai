import pytest
from backend.security.subject_resolution import names_a_person

class _Actor:
    employee_id = 1

# Real values from tickora_ai_dev, with the curly-apostrophe case included.
KNOWN = frozenset({
    "Casual Leave", "Sick Leave", "Earned Leave", "Unpaid Leave",
    "Christmas Day", "Gandhi Jayanti", "Independence Day", "Labour Day",
    "New Year's Day", "Republic Day",
    "Salary Advance", "Emergency Loan", "Penalty Deduction",
})

@pytest.mark.parametrize("question", [
    "How many Casual Leave days do I have?",
    "What is my Sick Leave balance?",
    "Is Gandhi Jayanti a holiday?",
    "Is New Year\u2019s Day a holiday?",
    "Is New Year's Day a holiday?",
    "What is my Emergency Loan remaining amount?",
    "What amount has been deducted from my Penalty Deduction?",
    "Is October 31 a holiday?",
    "Show my leave balance",
])
def test_known_terms_and_calendar_questions_do_not_name_a_person(question):
    assert names_a_person(question, _Actor(), KNOWN) is False

@pytest.mark.parametrize("question", [
    "Show Ravi Patel's attendance for October",
    "Show Myra Krishnan\u2019s attendance for October",
    "What is the Casual Leave balance for Myra Krishnan?",
])
def test_real_colleague_names_are_still_detected(question):
    assert names_a_person(question, _Actor(), KNOWN) is True

def test_other_employee_code_is_detected():
    assert names_a_person("Show EMP011 attendance", _Actor(), KNOWN) is True

def test_own_employee_code_is_not_another_person():
    assert names_a_person("Show EMP001 attendance", _Actor(), KNOWN) is False

@pytest.mark.parametrize("question", [
    "Show the meera's assigned task",
    "Show Meera's assigned task",
])
def test_single_name_possessives_are_detected(question):
    assert names_a_person(question, _Actor(), KNOWN) is True

@pytest.mark.parametrize("question", [
    "What is today's attendance?",
    "Show my employee's assigned task",
])
def test_common_possessives_are_not_mistaken_for_people(question):
    assert names_a_person(question, _Actor(), KNOWN) is False