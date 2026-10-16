import re
from datetime import date, datetime
from calendar import monthrange
from pydantic import ValidationError
from ai_model.intents import IntentRequest

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

STATUS_PATTERNS = {
    "PRESENT": r"\bpresent\b",
    "ABSENT": r"\babsent\b|\babsence\b",
    "LATE": r"\blate\b",
    "HALF_DAY": r"\bhalf[- ]day\b",
    "ON_LEAVE": r"\bon leave\b",
    "HOLIDAY": r"\bholidays?\b",
    "WEEKEND": r"\bweekends?\b",
    "DRAFT": r"\bdrafts?\b",
    "SUBMITTED": r"\bsubmitted\b",
    "APPROVED": r"\bapproved\b",
    "REJECTED": r"\brejected\b",
    "PENDING": r"\bpending\b",
    "CANCELLED": r"\bcancelled\b|\bcanceled\b",
}

def extract_period(text: str):
    text = text.lower()

    if re.search(r"\btoday\b", text):
        return "today"

    if re.search(r"\byesterday\b", text):
        return "yesterday"

    if re.search(r"\bthis week\b|\bcurrent week\b", text):
        return "this_week"

    if re.search(r"\bthis month\b|\bcurrent month\b", text):
        return "this_month"

    if re.search(r"\blast month\b|previous month\b", text):
        return "last_month"

    return None

def extract_status(text: str):
    text = text.lower()
    matches = [
        status
        for status, pattern in STATUS_PATTERNS.items()
        if re.search(pattern, text)
    ]

    # Avoid guessing when the question contains conflicting statuses.
    if len(matches) == 1:
        return matches[0]

    return None

def extract_explicit_date(text: str):
    # ISO format: 2026-10-21
    iso_match = re.search(
        r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b",
        text,
    )
    if iso_match:
        try:
            return date(
                int(iso_match.group(1)),
                int(iso_match.group(2)),
                int(iso_match.group(3)),
            )
        except ValueError:
            return None

    # Month name and day: October 21 or October 21, 2026
    month_pattern = "|".join(MONTHS)
    month_match = re.search(
        rf"\b({month_pattern})\s+(\d{{1,2}})"
        rf"(?:,?\s+(20\d{{2}}))?\b",
        text,
        re.IGNORECASE,
    )

    if month_match:
        month = MONTHS[month_match.group(1).lower()]
        day = int(month_match.group(2))
        year = int(month_match.group(3)) if month_match.group(3) else date.today().year

        try:
            return date(year, month, day)
        except ValueError:
            return None

    # Numeric format: 21/10/2026
    numeric_match = re.search(
        r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b",
        text,
    )
    if numeric_match:
        try:
            return date(
                int(numeric_match.group(3)),
                int(numeric_match.group(2)),
                int(numeric_match.group(1)),
            )
        except ValueError:
            return None

    return None

def extract_month_range(text: str):
    """Return the first day and last day of an explicitly named month."""
    text = text.lower()
    month_pattern = "|".join(MONTHS)

    match = re.search(
        rf"\b({month_pattern})\b(?:\s+(20\d{{2}}))?",
        text,
    )
    if not match:
        return None

    month = MONTHS[match.group(1)]
    year = int(match.group(2)) if match.group(2) else date.today().year

    return (
        date(year, month, 1),
        date(year, month, monthrange(year, month)[1]),
    )

def extract_region(text: str):
    """Prototype region extraction for common holiday questions."""
    match = re.search(
        r"\b(?:in|for)\s+"
        r"(India|Tamil Nadu|Chennai|Karnataka|"
        r"Maharashtra|Delhi|United States|USA|UK)\b",
        text,
        re.IGNORECASE,
    )

    if match:
        return match.group(1)

    return None

def extract_requested_metric(text: str, intent: str) -> str | None:
    """Identify the information requested by the user."""
    text = text.lower()

    metric_patterns = {
        "absent_days": r"\babsent\b|\babsence\b",
        "present_days": r"\bpresent\b",
        "late_days": r"\blate\b",
        "half_days": r"\bhalf[- ]days?\b",
        "leave_days": r"\bleave days?\b",
        "wfh_days": r"\bwfh days?\b|work[- ]from[- ]home days?",
        "recorded_days": r"\brecorded days?\b",
    }

    if intent in {"attendance_summary", "attendance_records"}:
        for metric, pattern in metric_patterns.items():
            if re.search(pattern, text):
                return metric

    count_question = re.search(
        r"\bhow many\b|\bcount\b|\bnumber of\b|\btotal number\b",
        text,
    )

    if count_question:
        return "record_count"

    return None

def extract_parameters(text: str, intent: str) -> dict:
    """
    Extract candidate parameters only.
    The returned values must still pass IntentRequest validation.
    """
    result = {"intent": intent}
    requested_metric = extract_requested_metric(text, intent)

    if requested_metric:
        result["requested_metric"] = requested_metric

    period = extract_period(text)
    status = None

    # Status filters are not applicable to holiday lookup.
    if intent != "holiday_lookup":
        status = extract_status(text)
    explicit_date = extract_explicit_date(text)

    if period:
        result["period"] = period

    if status:
        result["status"] = status

    if intent == "schedule_lookup":
        if explicit_date:
            result["on_date"] = explicit_date.isoformat()
        elif period in {"today", "yesterday"}:
            result["period"] = period

    elif intent == "holiday_lookup":
        region = extract_region(text)
        if region:
            result["region"] = region

        if explicit_date:
            result["on_date"] = explicit_date.isoformat()

    if explicit_date and intent not in {
        "schedule_lookup",
        "holiday_lookup",
    }:
        result["on_date"] = explicit_date.isoformat()

    # For explicit month queries, create a date range.
    # Do not overwrite an explicit single-day query.
    if not explicit_date and period is None:
        month_range = extract_month_range(text)

        if month_range and intent in {
            "attendance_records",
            "attendance_summary",
            "timesheet_lookup",
            "leave_status",
            "wfh_status",
        }:
            result["period"] = "custom"
            result["start_date"] = month_range[0].isoformat()
            result["end_date"] = month_range[1].isoformat()

    return result

def parse_request(text: str, intent: str):
    """
    Return a validated IntentRequest or a clear validation error.
    This function does not access the database.
    """
    candidate = extract_parameters(text, intent)

    try:
        return IntentRequest.model_validate(candidate)
    except ValidationError as exc:
        return {
            "error": "parameter_validation_failed",
            "details": exc.errors(include_url=False),
            "candidate": candidate,
        }

if __name__ == "__main__":
    examples = [
        ("Show my pending leave applications this month", "leave_status"),
        ("Show my detailed attendance records today", "attendance_records"),
        ("What is my work schedule on October 21, 2026", "schedule_lookup"),
        ("Show my cancelled WFH requests", "wfh_status"),
        ("List holidays in India", "holiday_lookup"),
    ]

    for question, intent in examples:
        print(f"\nQuestion: {question}")
        print(parse_request(question, intent))
