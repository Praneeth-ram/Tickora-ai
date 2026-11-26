import unittest
# from unittest.mock import patch

from backend.services.ambiguity import entity_clarification, missing_period_question


DATE_OPS = frozenset({
    "attendance.list", "attendance.count", "leave_request.list", "wfh_request.list",
    "timesheet.list", "task.list", "payroll_summary.list", "holiday.list",
})


class TestMissingPeriod(unittest.TestCase):
    def test_every_date_based_entity_asks_when_no_period(self):
        for op in DATE_OPS - {"holiday.list"}:
            message = missing_period_question(op, False, "show it", DATE_OPS)
            self.assertIn("Which period", message, op)

    def test_label_matches_the_entity(self):
        self.assertIn("your attendance", missing_period_question("attendance.list", False, "", DATE_OPS))
        self.assertIn("your payroll", missing_period_question("payroll_summary.list", False, "", DATE_OPS))
        self.assertIn("your tasks", missing_period_question("task.list", False, "", DATE_OPS))

    def test_period_given_or_inherited_never_asks(self):
        for op in DATE_OPS:
            self.assertIsNone(missing_period_question(op, True, "", DATE_OPS), op)

    def test_non_date_operations_and_holidays_never_ask(self):
        for op in ("leave_balance.list", "loan_request.list", "holiday.list", "holiday.count", None):
            self.assertIsNone(missing_period_question(op, False, "", DATE_OPS), op)

    def test_wording_that_states_a_period_never_asks(self):
        for question in ("Show my upcoming leave", "How many tasks so far", "total absent days ever",
                         "my remaining leave requests", "attendance to date"):
            self.assertIsNone(missing_period_question("attendance.list", False, question, DATE_OPS), question)


class TestEntityClarification(unittest.TestCase):
    def test_generic_request_asks_for_the_topic(self):
        for question in ("Show my records", "Show my records for November", "give me my details"):
            self.assertIn("What would you like to see", entity_clarification(question), question)

    def test_named_entity_never_asks(self):
        for question in (
            "Show my attendance records", "leave history", "Show my payroll summary",
            "task details", "How many days was I absent?", "Show my timesheet data",
        ):
            self.assertIsNone(entity_clarification(question), question)

    def test_unrelated_text_is_left_to_existing_rejection(self):
        self.assertIsNone(entity_clarification("What is the weather today?"))


class TestValidatePlan(unittest.TestCase):
    def test_validate_plan_flags_missing_period_and_keeps_old_calls_working(self):
        from backend.services.llm_chat_service import validate_plan

        plan = {"operation_id": "payroll_summary.list", "filters": {}}
        self.assertEqual(validate_plan(plan)[0], "ok")  # old one-argument call
        status, ask = validate_plan(plan, has_period=False)
        self.assertEqual(status, "missing_info")
        self.assertIn("Which period", ask)
        status, ask = validate_plan({"operation_id": "attendance.list"}, has_period=False)
        self.assertEqual(status, "missing_info")
        self.assertIn("your attendance", ask)
        self.assertEqual(validate_plan({"operation_id": "leave_balance.list"}, has_period=False), ("ok", None))
        self.assertEqual(
            validate_plan({"operation_id": "attendance.list"}, False, "show my upcoming leave"), ("ok", None)
        )


if __name__ == "__main__":
    unittest.main()
