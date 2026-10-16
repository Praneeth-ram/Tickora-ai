from datetime import date, datetime
from typing import Any

def format_date(value: Any) -> str:
    """Format dates for user-facing responses."""
    if isinstance(value, (date, datetime)):
        return value.strftime("%d %b %Y")
    return str(value) if value is not None else "N/A"

def format_time(value: Any) -> str:
    """Format timestamps for user-facing responses."""
    if isinstance(value, datetime):
        return value.strftime("%I:%M %p")
    return str(value) if value is not None else "Not recorded"

def format_attendance(records: list[dict]) -> str:
    if not records:
        return "No attendance records were found for the requested period."

    lines = [f"I found {len(records)} attendance record(s):"]
    for record in records:
        work_date = format_date(record.get("work_date"))
        status = record.get("status", "Unknown")
        clock_in = format_time(record.get("clock_in"))
        clock_out = format_time(record.get("clock_out"))
        location = record.get("work_location", "Not specified")

        lines.append(
            f"- {work_date}: {status}. "
            f"Clock-in: {clock_in}; clock-out: {clock_out}. "
            f"Location: {location}."
        )

    return "\n".join(lines)

def format_attendance_summary(data: dict) -> str:
    if not data:
        return "No attendance summary is available for the requested period."

    return (
        "Here is your attendance summary:\n"
        f"- Recorded days: {data.get('recorded_days', 0)}\n"
        f"- Present days: {data.get('present_days', 0)}\n"
        f"- Absent days: {data.get('absent_days', 0)}\n"
        f"- Late days: {data.get('late_days', 0)}\n"
        f"- Half days: {data.get('half_days', 0)}\n"
        f"- Leave days: {data.get('leave_days', 0)}\n"
        f"- WFH days: {data.get('wfh_days', 0)}"
    )


def format_records(
    data: list[dict],
    title: str,
    date_fields: tuple[str, ...] = (),
) -> str:
    if not data:
        empty_messages = {
            "leave request(s)": "You have no matching leave requests.",
            "work-from-home request(s)": "You have no matching WFH requests.",
            "timesheet record(s)": "No matching timesheet entries were found.",
            "holiday(s)": "No holidays were found for the requested period.",
            "work schedule record(s)": "No work schedule records were found.",
        }
        return empty_messages.get(
            title,
            f"No matching {title} were found.",
        )

    lines = [f"I found {len(data)} {title}:"]

    for index, record in enumerate(data, start=1):
        details = []

        for key, value in record.items():
            if key in date_fields:
                value = format_date(value)
            elif isinstance(value, datetime):
                value = format_time(value)

            if value is not None:
                label = key.replace("_", " ").capitalize()
                details.append(f"{label}: {value}")

        lines.append(f"{index}. " + "; ".join(details))

    return "\n".join(lines)

def format_requested_metric(metric: str, data: Any) -> str | None:
    """Format a specifically requested metric from retrieved data."""
    if not metric:
        return None

    labels = {
        "recorded_days": "Recorded days",
        "present_days": "Present days",
        "absent_days": "Absent days",
        "late_days": "Late days",
        "half_days": "Half days",
        "leave_days": "Leave days",
        "wfh_days": "Work-from-home days",
    }

    if isinstance(data, dict) and metric in labels:
        value = data.get(metric, 0)
        return f"{labels[metric]}: {value}."

    if metric == "record_count" and isinstance(data, list):
        return f"Found {len(data)} matching record(s)."

    return None

def format_chat_response(result: dict) -> dict:
    """Add a readable answer while preserving the existing API response."""
    if not result.get("success"):
        result["answer"] = result.get(
            "message", "Sorry, I couldn't process that request."
        )
        return result

    intent = result.get("intent")
    data = result.get("data", [])
    requested_metric = result.get("requested_metric")

    metric_answer = format_requested_metric(
        requested_metric,
        data,
    )

    if metric_answer is not None:
        result["answer"] = metric_answer
        return result

    if intent == "attendance_records":
        answer = format_attendance(data)

    elif intent == "attendance_summary":
        answer = format_attendance_summary(data)

    elif intent == "timesheet_lookup":
        answer = format_records(
            data, "timesheet record(s)", ("work_date", "date")
        )

    elif intent == "leave_status":
        answer = format_records(
            data, "leave request(s)", ("start_date", "end_date", "created_at")
        )

    elif intent == "wfh_status":
        answer = format_records(
            data, "work-from-home request(s)", ("start_date", "end_date", "created_at")
        )

    elif intent == "holiday_lookup":
        answer = format_records(
            data, "holiday(s)", ("holiday_date", "date")
        )

    elif intent == "schedule_lookup":
        answer = format_records(
            data, "work schedule record(s)", ("work_date", "schedule_date", "date")
        )

    else:
        answer = result.get("message", "Your request was processed.")

    result["answer"] = answer
    return result
