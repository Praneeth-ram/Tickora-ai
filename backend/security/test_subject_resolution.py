import unittest
from unittest.mock import MagicMock
from backend.security.access_policy import Actor, SUPER_ADMIN
from backend.security.subject_resolution import names_a_person, resolve_subject


class _Actor:
    employee_id = 1
    employee_code = "EMP001"


KNOWN = frozenset({
    "Casual Leave", "Sick Leave", "Earned Leave", "Unpaid Leave",
    "Christmas Day", "Gandhi Jayanti", "Independence Day", "Labour Day",
    "New Year's Day", "Republic Day",
    "Salary Advance", "Emergency Loan", "Penalty Deduction",
})


class TestSubjectResolution(unittest.TestCase):
    def test_super_admin_self_reference_resolves_to_actor(self):
        connection = MagicMock()
        connection.execute.return_value.mappings.return_value.all.return_value = [
            {"id": 1, "employee_code": "EMP001", "full_name": "Admin User"}
        ]
        subject_id = resolve_subject(
            connection,
            Actor(employee_id=1, organization_id=1, department_id=1,
                  role=SUPER_ADMIN, employee_code="EMP001"),
            "Show my payroll for September",
        )
        self.assertEqual(subject_id, 1)

    def test_known_terms_and_calendar_questions_do_not_name_a_person(self):
        questions = [
            "How many Casual Leave days do I have?",
            "What is my Sick Leave balance?",
            "Is Gandhi Jayanti a holiday?",
            "Is New Year\u2019s Day a holiday?",
            "Is New Year's Day a holiday?",
            "What is my Emergency Loan remaining amount?",
            "What amount has been deducted from my Penalty Deduction?",
            "Is October 31 a holiday?",
            "Is October a leave month?",
            "Show attendance for October",
            "Show my leave balance",
        ]
        for question in questions:
            with self.subTest(question=question):
                self.assertFalse(names_a_person(question, _Actor(), KNOWN))

    def test_real_colleague_names_are_still_detected(self):
        questions = [
            "Show Ravi Patel's attendance for October",
            "Show Myra Krishnan\u2019s attendance for October",
            "What is the Casual Leave balance for Myra Krishnan?",
            "What is Ravi Kumar's salary?",
        ]
        for question in questions:
            with self.subTest(question=question):
                self.assertTrue(names_a_person(question, _Actor(), KNOWN))

    def test_other_employee_code_is_detected(self):
        self.assertTrue(names_a_person("Show EMP011 attendance", _Actor(), KNOWN))

    def test_own_employee_code_is_not_another_person(self):
        self.assertFalse(names_a_person("Show EMP001 attendance", _Actor(), KNOWN))

    def test_single_name_possessives_are_detected(self):
        for question in ["Show Meera's assigned task", "Show the meera's assigned task"]:
            with self.subTest(question=question):
                self.assertTrue(names_a_person(question, _Actor(), KNOWN))

    def test_common_possessives_are_not_mistaken_for_people(self):
        for question in ["What is today's attendance?", "Show my employee's assigned task"]:
            with self.subTest(question=question):
                self.assertFalse(names_a_person(question, _Actor(), KNOWN))


if __name__ == "__main__":
    unittest.main()