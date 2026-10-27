import re
from datetime import date, datetime, time
from typing import Any


def format_date(value: Any) -> str:
    """Format dates for user-facing responses."""
    if isinstance(value, (date, datetime)):
        return value.strftime("%d %b %Y")
    return str(value) if value is not None else "N/A"


def format_date_range(start: Any, end: Any) -> str:
    """Format single-day or start-to-end date ranges cleanly."""
    start_str = format_date(start)
    end_str = format_date(end)
    if start_str == end_str or not end:
        return start_str
    return f"{start_str} to {end_str}"


def format_time(value: Any) -> str:
    """Format timestamps and times for user-facing responses."""
    if isinstance(value, (datetime, time)):
        return value.strftime("%I:%M %p")
    return str(value) if value is not None else "Not recorded"


def format_workdays(days: Any) -> str:
    """Convert numeric weekday lists into human-readable strings."""
    if not days or not isinstance(days, list):
        return "Not specified"

    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    sorted_days = sorted(days)

    if sorted_days == [1, 2, 3, 4, 5]:
        return "Monday to Friday"
    if sorted_days == [1, 2, 3, 4, 5, 6]:
        return "Monday to Saturday"
    if sorted_days == [1, 2, 3, 4, 5, 6, 7]:
        return "Every day (Mon–Sun)"

    formatted = [day_names[d - 1] for d in sorted_days if 1 <= d <= 7]
    return ", ".join(formatted)


def format_status_badge(status: str | None) -> str:
    """Format a status with a clean readable label and emoji."""
    if not status:
        return "Unknown"
    normalized = status.upper()
    badges = {
        "APPROVED": "Approved",
        "PENDING": "Pending",
        "REJECTED": "Rejected",
        "CANCELLED": "Cancelled",
        "PRESENT": "Present",
        "ABSENT": "Absent",
        "LATE": "Late",
        "HALF_DAY": "Half-day",
        "ON_LEAVE": "On Leave",
        "SUBMITTED": "Submitted",
        "DRAFT": "Draft",
    }
    return badges.get(normalized, normalized.capitalize())


def format_attendance(records: list[dict], status: str | None = None, question: str = "") -> str:
    """Format attendance records cleanly."""
    if not records:
        if status:
            return f"No {status.lower().replace('_', ' ')} records were found for the requested period."
        if re.search(r"\b(?:absent|absence)\b", question.lower()):
            return "No absent records were found for the requested period (0 absences recorded)."
        return "No attendance records were found for the requested period."

    lines = [f"I found {len(records)} attendance record(s):"]
    for record in records:
        work_date = format_date(record.get("work_date"))
        raw_status = record.get("status", "Unknown")
        status_label = format_status_badge(raw_status)
        clock_in = format_time(record.get("clock_in"))
        clock_out = format_time(record.get("clock_out"))
        location = record.get("work_location", "Office").capitalize()

        lines.append(
            f"- {work_date}: {status_label} ({location}) | In: {clock_in}, Out: {clock_out}"
        )

    return "\n".join(lines)


def format_attendance_summary(data: dict, requested_metric: str | None = None, question: str = "") -> str:
    """Format attendance summary or specific metrics cleanly."""
    if not data:
        return "No attendance summary is available for the requested period."

    q_lower = question.lower()

    if requested_metric == "absent_days":
        count = data.get("absent_days", 0)
        if re.search(r"\b(?:is|was|were|did|have i been)\b", q_lower):
            if count == 0:
                return "No, you have 0 absent days for this period (you attended all recorded days)."
            return f"Yes, you have {count} absent day(s) recorded for this period."
        return f"You have {count} absent day(s) recorded for this period."

    if requested_metric == "late_days":
        count = data.get("late_days", 0)
        if count == 0:
            return "You have 0 late days recorded for this period."
        return f"You have {count} late day(s) recorded for this period."

    if requested_metric == "present_days":
        count = data.get("present_days", 0)
        return f"You have {count} present day(s) recorded for this period."

    if requested_metric == "wfh_days":
        count = data.get("wfh_days", 0)
        if re.search(r"\b(?:is|was|were|did|have i been)\b", q_lower) and not re.search(r"\b(?:how many|number of|count)\b", q_lower):
            if count == 0:
                return "No, you have 0 work-from-home days recorded for this period."
            return f"Yes, you have {count} work-from-home day(s) recorded for this period."
        return f"You have {count} work-from-home day(s) recorded for this period."

    if requested_metric == "leave_days":
        count = data.get("leave_days", 0)
        if re.search(r"\b(?:is|was|were|did|have i been|did i take)\b", q_lower) and not re.search(r"\b(?:how many|number of|count)\b", q_lower):
            if count == 0:
                return "No, you have 0 leave days recorded for this period."
            return f"Yes, you have {count} leave day(s) recorded for this period."
        return f"You have {count} leave day(s) recorded for this period."

    if requested_metric == "recorded_days":
        count = data.get("recorded_days", 0)
        return f"You have {count} total recorded day(s) for this period."

    return (
        "Here is your attendance summary:\n"
        f"- Present days: {data.get('present_days', 0)}\n"
        f"- Absent days: {data.get('absent_days', 0)}\n"
        f"- Late days: {data.get('late_days', 0)}\n"
        f"- Work-from-home (WFH) days: {data.get('wfh_days', 0)}\n"
        f"- Leave days: {data.get('leave_days', 0)}\n"
        f"- Half days: {data.get('half_days', 0)}\n"
        f"- Total recorded days: {data.get('recorded_days', 0)}"
    )


def format_leave_requests(data: list[dict], status: str | None = None, question: str = "") -> str:
    """Format leave requests in a clean, human-readable structure."""
    if not data:
        if status:
            return f"You have no {status.lower()} leave requests."
        return "You have no matching leave requests."

    q_lower = question.lower()

    # Direct confirmation check if user asks "was my leave approved / pending"
    if re.search(r"\b(?:approved|accepted)\b", q_lower) and len(data) == 1:
        req = data[0]
        st = req.get("status", "").upper()
        l_type = req.get("leave_type", "Leave").capitalize()
        dates = format_date_range(req.get("start_date"), req.get("end_date"))
        if st == "APPROVED":
            return f"Yes, your {l_type} request for {dates} is Approved."
        return f"Your {l_type} request for {dates} is currently {format_status_badge(st)}."

    lines = [f"You have {len(data)} leave request(s):"]
    for record in data:
        leave_type = record.get("leave_type", "Leave").capitalize()
        dates = format_date_range(record.get("start_date"), record.get("end_date"))
        status_label = format_status_badge(record.get("status"))
        reason = record.get("reason") or "No reason provided"
        requested_at = format_date(record.get("requested_at"))

        lines.append(
            f"- {leave_type} ({dates}):\n"
            f"  - Status: {status_label}\n"
            f"  - Reason: {reason}\n"
            f"  - Requested: {requested_at}"
        )

    return "\n".join(lines)


def format_wfh_requests(data: list[dict], status: str | None = None, question: str = "") -> str:
    """Format work-from-home requests cleanly."""
    if not data:
        if status:
            return f"You have no {status.lower()} work-from-home requests."
        return "You have no matching work-from-home requests."

    q_lower = question.lower()

    # Direct answer if user asked specifically for the reason
    if re.search(r"\breason\b", q_lower) and len(data) == 1:
        record = data[0]
        dates = format_date_range(record.get("start_date"), record.get("end_date"))
        reason = record.get("reason", "Not specified")
        st = format_status_badge(record.get("status"))
        return f"Your reason for the WFH request on {dates} was: \"{reason}\" (Status: {st})."

    # Direct confirmation check if user asks "was my WFH approved?"
    if re.search(r"\b(?:approved|accepted)\b", q_lower) and len(data) == 1:
        record = data[0]
        dates = format_date_range(record.get("start_date"), record.get("end_date"))
        st = record.get("status", "").upper()
        if st == "APPROVED":
            return f"Yes, your work-from-home request for {dates} is Approved."
        return f"Your work-from-home request for {dates} is currently {format_status_badge(st)}."

    lines = [f"You have {len(data)} work-from-home request(s):"]
    for record in data:
        dates = format_date_range(record.get("start_date"), record.get("end_date"))
        status_label = format_status_badge(record.get("status"))
        reason = record.get("reason") or "No reason provided"
        requested_at = format_date(record.get("requested_at"))

        lines.append(
            f"- WFH on {dates}:\n"
            f"  - Status: {status_label}\n"
            f"  - Reason: {reason}\n"
            f"  - Requested: {requested_at}"
        )

    return "\n".join(lines)


def format_work_schedules(data: list[dict]) -> str:
    """Format work schedules clearly with shift timings and readable workdays."""
    if not data:
        return "No work schedule records were found."

    lines = ["Here is your active work schedule:"]
    for record in data:
        shift_start = format_time(record.get("shift_start"))
        shift_end = format_time(record.get("shift_end"))
        expected_hours = record.get("expected_hours", 8)
        workdays = format_workdays(record.get("workdays"))
        effective_from = format_date(record.get("effective_from"))

        lines.append(
            f"- Shift Timings: {shift_start} to {shift_end} ({expected_hours} hrs/day)\n"
            f"- Working Days: {workdays}\n"
            f"- Effective From: {effective_from}"
        )

    return "\n".join(lines)


def format_timesheets(data: list[dict]) -> str:
    """Format timesheet entries cleanly with totals."""
    if not data:
        return "No matching timesheet entries were found."

    total_hours = sum(float(r.get("hours_worked", 0)) for r in data)
    hours_str = f"{total_hours:.1f}".rstrip("0").rstrip(".")

    lines = [f"Found {len(data)} timesheet entry/entries (Total: {hours_str} hrs):"]
    for record in data:
        work_date = format_date(record.get("work_date"))
        hours = float(record.get("hours_worked", 0))
        hours_display = f"{hours:.1f}".rstrip("0").rstrip(".")
        desc = record.get("description") or "No description"
        status_label = format_status_badge(record.get("submission_status"))

        lines.append(f"- {work_date}: {hours_display} hrs | {desc} ({status_label})")

    return "\n".join(lines)


def format_holidays(data: list[dict], region: str | None = None, question: str = "") -> str:
    """Format holidays cleanly with natural answers for date checks."""
    q_lower = question.lower()

    if not data:
        # Check if the user was asking about a specific day
        date_match = re.search(
            r"\b(\d{1,2}(?:st|nd|rd|th)?[\s\-_]+[a-zA-Z]{3,9}(?:[\s\-_,]+20\d{2})?)\b",
            question,
            re.IGNORECASE,
        )
        if date_match:
            return f"No, {date_match.group(1)} is not a company holiday."
        if re.search(r"\bupcoming\b", q_lower):
            year_match = re.search(r"\b(20\d\d)\b", q_lower)
            if year_match:
                return f"There are no upcoming holidays in {year_match.group(1)}."
            return "There are no upcoming holidays for the requested period."
        if re.search(r"\b(?:is there|is|any holiday)\b", q_lower):
            return "No company holidays were found for that date."
        return "No holidays were found for the requested period."

    # Direct answer if user asked "is there any holiday on X?" and found 1 record
    if re.search(r"\b(?:is there|is|any holiday)\b", q_lower) and len(data) == 1:
        h_date = format_date(data[0].get("holiday_date"))
        name = data[0].get("holiday_name", "Holiday")
        reg = data[0].get("region", "")
        reg_info = f" ({reg})" if reg and not region else ""
        return f"Yes! {h_date} is a holiday: {name}{reg_info}."

    region_str = f" in {region}" if region else ""
    noun = "upcoming holiday(s)" if re.search(r"\bupcoming\b", q_lower) else "holiday(s)"
    lines = [f"Found {len(data)} {noun}{region_str}:"]

    for record in data:
        h_date = format_date(record.get("holiday_date"))
        name = record.get("holiday_name", "Holiday")
        h_region = record.get("region")
        reg_info = f" ({h_region})" if h_region and not region else ""

        lines.append(f"- {h_date}: {name}{reg_info}")

    return "\n".join(lines)


def format_requested_field(
    field: str | None,
    data: Any,
) -> str | None:
    """Format a specifically requested timestamp from database results."""
    if not field:
        return None

    labels = {
        "submitted_at": "Submission time",
        "approved_at": "Approval time",
        "clock_in": "Clock-in time",
        "clock_out": "Clock-out time",
        "created_at": "Creation time",
    }

    label = labels.get(field)
    if label is None:
        return None

    if not isinstance(data, list) or not data:
        return f"No records were found for the requested {label.lower()}."

    answers = []

    for record in data:
        value = record.get(field)

        if value is None:
            formatted_value = "Not recorded"
        elif isinstance(value, datetime):
            formatted_value = value.strftime("%d %b %Y at %I:%M %p")
        elif isinstance(value, date):
            formatted_value = value.strftime("%d %b %Y")
        elif isinstance(value, time):
            formatted_value = value.strftime("%I:%M %p")
        else:
            formatted_value = str(value)

        identifier = record.get(
            "timesheet_id",
            record.get("attendance_id"),
        )
        prefix = f"Record {identifier}: " if identifier is not None else ""

        answers.append(f"{prefix}{label}: {formatted_value}")

    return "\n".join(answers)

def format_chat_response(result: dict) -> dict:
    """Add a polished, human-readable answer while preserving structured data for the frontend."""
    if not result.get("success"):
        result["answer"] = result.get(
            "message", "Sorry, I couldn't process that request."
        )
        return result

    intent = result.get("intent")
    data = result.get("data", [])
    requested_metric = result.get("requested_metric")
    requested_field = result.get("requested_field")
    question = result.get("question", "")
    status = result.get("status")

    field_answer = format_requested_field(requested_field, data)
    if field_answer is not None:
        result["answer"] = field_answer
        return result

    if intent == "attendance_summary":
        answer = format_attendance_summary(data, requested_metric, question)

    elif intent == "work_location":
        answer = result.get(
            "message",
            "No work-location information was found.",
        )

    elif intent == "attendance_records":
        answer = format_attendance(data, status, question)

    elif intent == "timesheet_lookup":
        answer = format_timesheets(data)

    elif intent == "leave_status":
        answer = format_leave_requests(data, status, question)

    elif intent == "wfh_status":
        answer = format_wfh_requests(data, status, question)

    elif intent == "holiday_lookup":
        answer = format_holidays(data, result.get("region"), question)

    elif intent == "schedule_lookup":
        answer = format_work_schedules(data)

    else:
        answer = result.get("message", "Your request was processed.")

    result["answer"] = answer
    return result
