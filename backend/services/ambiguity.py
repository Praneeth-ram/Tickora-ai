"""Decide when a question is too unclear to run, and what to ask instead.

Pure functions only (no database, no model), so every rule is cheap to test.
Employee ambiguity is handled earlier by backend.security.subject_resolution.
"""
from __future__ import annotations

import re

# Operations that never need a period even though they have a date column: calendar lookups.
EXEMPT_FROM_PERIOD = frozenset({"holiday.list", "holiday.count"})

# Wording that already says which period is meant, even though it is not a calendar date.
PERIOD_FREE_RE = re.compile(
    r"\b(?:ever|overall|all[- ]time|so\s+far|to\s+date|till\s+date|upcoming|"
    r"coming\s+up|next|remaining|future)\b",
    re.IGNORECASE,
)

ENTITY_LABELS = {
    "attendance": "attendance",
    "leave_request": "leave requests",
    "wfh_request": "work from home requests",
    "timesheet": "timesheets",
    "task": "tasks",
    "payroll_summary": "payroll",
    "holiday": "holidays",
}

# A question that asks for "records"/"details" without saying of what.
GENERIC_NOUN_RE = re.compile(
    r"\b(?:records?|details?|info(?:rmation)?|data|history|report|summary|overview)\b",
    re.IGNORECASE,
)
ENTITY_WORD_RE = re.compile(
    r"\b(?:attend\w*|absen\w*|present|late|clock\w*|check[- ]?(?:in|out)|punch\w*|"
    r"leaves?|wfh|work\s+from\s+home|timesheets?|holidays?|payroll|salary|payslips?|"
    r"tasks?|loans?|overtime|employees?|directory)\b",
    re.IGNORECASE,
)

ENTITY_CHOICES = (
    "attendance, leave, work from home, timesheets, holidays, tasks, loans or payroll"
)


def missing_period_question(
    operation_id: str | None,
    has_period: bool,
    question: str = "",
    date_operations=frozenset(),
) -> str | None:
    """Ask for a period when the operation is date-based and none was given or inherited.

    date_operations is the set of operation ids that filter on a date (the caller passes
    OPERATION_DATE_FIELDS), so every date-based entity is covered without a second list.
    """
    if (
        not operation_id
        or has_period
        or operation_id not in date_operations
        or operation_id in EXEMPT_FROM_PERIOD
        or PERIOD_FREE_RE.search(question)
    ):
        return None
    label = ENTITY_LABELS.get(operation_id.split(".", 1)[0], "records")
    return (
        f"Which period should I use for your {label}? "
        f"For example: 'Show my {label} for October 2026'."
    )


def entity_clarification(question: str) -> str | None:
    """Return a question when the user wants 'records' but names no HR topic."""
    if ENTITY_WORD_RE.search(question) or not GENERIC_NOUN_RE.search(question):
        return None
    return (
        f"What would you like to see? I can look up {ENTITY_CHOICES}. "
        "For example: 'Show my attendance for November'."
    )
