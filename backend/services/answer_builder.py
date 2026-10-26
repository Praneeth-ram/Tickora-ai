"""Build plain-language answers for attendance questions."""

from collections import Counter
from datetime import date, datetime, time, timedelta
from typing import Any
from datetime import date, datetime, time, timedelta

MAX_LIST_ROWS = 31

STATUS_LABELS = {
    "PRESENT": "Present",
    "LATE": "Late",
    "ABSENT": "Absent",
    "HALF_DAY": "Half day",
    "ON_LEAVE": "On leave",
    "HOLIDAY": "Holiday",
    "WEEKEND": "Weekend",
}
LOCATION_LABELS = {"OFFICE": "Office", "WFH": "Work from home", "FIELD": "Field"}
CLOCKED_STATUSES = {"PRESENT", "LATE", "HALF_DAY"}


def fmt_day(d: date) -> str:
    """Example: 'Monday, 19 October 2026'."""
    return f"{d.strftime('%A')}, {d.day} {d.strftime('%B %Y')}"


def fmt_range(start: date, end: date) -> str:
    """Examples: 'October 2026', '1 to 15 October 2026', '19 October 2026'."""
    if start == end:
        return f"{start.day} {start.strftime('%B %Y')}"
    last_of_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    if start.day == 1 and end == last_of_month and start.month == end.month:
        return start.strftime("%B %Y")
    if start.month == end.month and start.year == end.year:
        return f"{start.day} to {end.day} {end.strftime('%B %Y')}"
    return f"{start.day} {start.strftime('%B %Y')} to {end.day} {end.strftime('%B %Y')}"


def _row_date(row: dict[str, Any]) -> date | None:
    value = row.get("attendance_date") or row.get("work_date")
    if isinstance(value, datetime):
        return value.date()
    return value if isinstance(value, date) else None


def fmt_clock(value: Any, tz) -> str | None:
    """Convert a stored timestamp to local time and format it as '9:20 AM'."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None and tz is not None:
            value = value.astimezone(tz)
    elif not isinstance(value, time):
        return None
    return f"{(value.hour % 12) or 12}:{value.minute:02d} {'AM' if value.hour < 12 else 'PM'}"


def status_text(status: str | None, location: str | None) -> str:
    label = STATUS_LABELS.get((status or "").upper(), (status or "Unknown").replace("_", " ").title())
    if (status or "").upper() in CLOCKED_STATUSES and location:
        loc = LOCATION_LABELS.get(location.upper(), location.title())
        return f"{label} ({loc})"
    return label


def single_day_answer(kind: str, day: date, row: dict[str, Any] | None, tz) -> str:
    """One sentence answering a question about a single day. kind: clock_in, clock_out, status."""
    when = fmt_day(day)
    if row is None:
        return f"I couldn't find an attendance record for {when}."

    status = row.get("status")
    cin = fmt_clock(row.get("clock_in"), tz)
    cout = fmt_clock(row.get("clock_out"), tz)
    status_desc = status_text(status, row.get("work_location"))

    if kind == "clock_in":
        if cin:
            return f"Your clock-in time on {when} was {cin}."
        return f"You have no clock-in recorded for {when}; your status that day was {status_desc}."

    if kind == "clock_out":
        if cout:
            return f"Your clock-out time on {when} was {cout}."
        return f"You have no clock-out recorded for {when}; your status that day was {status_desc}."

    sentence = f"On {when}, your attendance status was {status_desc}."
    times = []
    if cin:
        times.append(f"clocked in at {cin}")
    if cout:
        times.append(f"clocked out at {cout}")
    if times:
        sentence += " You " + " and ".join(times) + "."
    return sentence


def range_summary_answer(rows: list[dict[str, Any]], start: date, end: date) -> str:
    span = fmt_range(start, end)
    if not rows:
        return f"I couldn't find any attendance records for {span}."

    counts = Counter((row.get("status") or "UNKNOWN").upper() for row in rows)
    parts = [
        f"{count} {STATUS_LABELS.get(status, status.title()).lower()}"
        for status, count in counts.most_common()
    ]
    total = len(rows)
    noun = "record" if total == 1 else "records"
    return (
        f"For {span} you have {total} attendance {noun}: "
        f"{', '.join(parts)}. "
        "Ask me to show the list if you want the day-by-day details."
    )

def _days_in_range(start: date, end: date) -> list[date]:
    days = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


def _rows_by_day(rows: list[dict[str, Any]]) -> dict[date, dict[str, Any]]:
    by_day: dict[date, dict[str, Any]] = {}
    for row in rows:
        day = _row_date(row)
        if day is not None:
            by_day.setdefault(day, row)
    return by_day


def _day_label(day: date) -> str:
    return f"{day.day} {day.strftime('%b %Y')}"


def range_list_answer(rows: list[dict[str, Any]], start: date, end: date, tz) -> str:
    """One line per day in the range. Days with no record are shown as such."""
    span = fmt_range(start, end)
    if not rows:
        return f"I couldn't find any attendance records for {span}."

    by_day = _rows_by_day(rows)
    days = _days_in_range(start, end)
    note = ""
    if len(days) > MAX_LIST_ROWS:
        days = sorted(by_day)
        note = f"Showing the {len(days)} days with records."

    lines = [f"Your attendance for {span}:"]
    for day in days:
        row = by_day.get(day)
        if row is None:
            lines.append(f"- {_day_label(day)}: no attendance record")
            continue
        cin = fmt_clock(row.get("clock_in"), tz) or "-"
        cout = fmt_clock(row.get("clock_out"), tz) or "-"
        lines.append(
            f"- {_day_label(day)}: {status_text(row.get('status'), row.get('work_location'))} "
            f"| In: {cin} | Out: {cout}"
        )
    if note:
        lines.append(note)
    return "\n".join(lines)


def range_clock_answer(rows: list[dict[str, Any]], start: date, end: date, kind: str, tz) -> str:
    """One line per day in the range with the clock-in or clock-out time."""
    span = fmt_range(start, end)
    label = "clock-in" if kind == "clock_in" else "clock-out"
    field = "clock_in" if kind == "clock_in" else "clock_out"
    if not rows:
        return f"I couldn't find any attendance records for {span}."

    by_day = _rows_by_day(rows)
    days = _days_in_range(start, end)
    note = ""
    if len(days) > MAX_LIST_ROWS:
        days = sorted(by_day)
        note = f"Showing the {len(days)} days with records."

    lines = [f"Your {label} times for {span}:"]
    for day in days:
        row = by_day.get(day)
        if row is None:
            lines.append(f"- {_day_label(day)}: no attendance record")
            continue
        value = fmt_clock(row.get(field), tz)
        lines.append(f"- {_day_label(day)}: {value or 'no ' + label + ' recorded'}")
    if note:
        lines.append(note)
    return "\n".join(lines)
    
def range_clock_answer(rows: list[dict[str, Any]], start: date, end: date, kind: str, tz) -> str:
    span = fmt_range(start, end)
    label = "clock-in" if kind == "clock_in" else "clock-out"
    field = "clock_in" if kind == "clock_in" else "clock_out"
    if not rows:
        return f"I couldn't find any attendance records for {span}."

    shown = rows[:MAX_LIST_ROWS]
    lines = [f"Your {label} times for {span}:"]
    for row in shown:
        d = _row_date(row)
        day_text = f"{d.day} {d.strftime('%b %Y')}" if d else "Unknown date"
        value = fmt_clock(row.get(field), tz)
        lines.append(f"- {day_text}: {value or 'no ' + label + ' recorded'}")
    if len(rows) > len(shown):
        lines.append(f"Showing {len(shown)} of {len(rows)} records.")
    return "\n".join(lines)

def group_by_summary_answer(rows: list[dict[str, Any]], span: str, group_key: str, total: int) -> str:
    """
    Build a summary answer for group_by operations.
    
    Args:
        rows: List of aggregated results (should already be grouped)
        span: The date range text (e.g., "this month", "October 2026")
        group_key: The field that was grouped by (e.g., "status")
        total: Total number of records
    """
    if not rows:
        return f"No attendance records found for {span}."

    # Determine the type of data we're working with
    first_row = rows[0]
    is_numeric = isinstance(first_row.get('count'), (int, float))
    
    # Build human-readable group key header
    group_key_display = group_key.replace('_', ' ').title()
    
    # Determine if we have a nested summary (e.g., status -> location)
    has_nested = False
    nested_key = None
    if len(first_row) > 1:
        # Find the nested key (anything other than 'count' or the group_key)
        for key in first_row.keys():
            if key != 'count' and key != group_key:
                has_nested = True
                nested_key = key
                break

    # Build header
    lines = [f"Your attendance summary for {span}:"]
    lines.append(f"Grouped by: {group_key_display}")
    if total > 0:
        lines.append(f"Total records: {total}")
    
    # Build item rows
    if is_numeric:
        # Numeric aggregation (e.g., sum of hours)
        for row in rows:
            group_value = row.get(group_key, 'Unknown')
            count = row.get('count', 0)
            total_value = row.get('total', 0)
            
            if has_nested and nested_key:
                nested_value = row.get(nested_key, 'Unknown')
                nested_label = nested_value.replace('_', ' ').title() if isinstance(nested_value, str) else nested_value
                lines.append(f"- {group_value} ({nested_label}): {total_value} hours")
            else:
                lines.append(f"- {group_value}: {total_value} hours")
    else:
        # Non-numeric aggregation (e.g., counts)
        for row in rows:
            group_value = row.get(group_key, 'Unknown')
            count = row.get('count', 0)
            
            if has_nested and nested_key:
                nested_value = row.get(nested_key, 'Unknown')
                nested_label = nested_value.replace('_', ' ').title() if isinstance(nested_value, str) else nested_value
                lines.append(f"- {group_value} ({nested_label}): {count} {'day' if count == 1 else 'days'}")
            else:
                label = group_value.replace('_', ' ').title() if isinstance(group_value, str) else group_value
                lines.append(f"- {label}: {count} {'day' if count == 1 else 'days'}")

    return "\n".join(lines)