from backend.security.subject_resolution import match_subject

ROWS = [
    {"id": 2, "employee_code": "EMP002", "full_name": "Diya Iyer"},
    {"id": 11, "employee_code": "EMP011", "full_name": "Reyansh Verma"},
    {"id": 12, "employee_code": "EMP012", "full_name": "Myra Krishnan"},
    {"id": 3, "employee_code": "EMP003", "full_name": "Arjun Kumar"},
    {"id": 13, "employee_code": "EMP013", "full_name": "Advait Shah"},
]


def test_full_name_is_matched():
    assert match_subject(ROWS, "Show Myra Krishnan's attendance for October") == 12


def test_employee_code_is_matched():
    assert match_subject(ROWS, "Show EMP011 attendance for October") == 11


def test_unknown_name_returns_none():
    assert match_subject(ROWS, "Show Ravi Patel's attendance") is None


def test_ambiguous_first_name_returns_none():
    rows = ROWS + [{"id": 20, "employee_code": "EMP020", "full_name": "Myra Gupta"}]
    assert match_subject(rows, "Show Myra's attendance") is None


def test_question_without_a_name_returns_none():
    assert match_subject(ROWS, "Show my attendance for October") is None