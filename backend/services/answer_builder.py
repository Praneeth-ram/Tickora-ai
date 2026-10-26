"""Build plain-language answers for attendance questions.

Answers answer the question that was asked. A single-day question gets one
sentence. A range question gets a summary sentence by default, and a day-by-day
list only when the user explicitly asks to see it.
"""

from collections import Counter
from datetime import date, datetime, time, timedelta
from typing import Any

MAX_LIST_ROWS = 31
# An empty range up to this many days is listed day by day; longer empty ranges get one sentence.
EMPTY_DAY_LISTING_LIMIT = 7

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
    """One sentence answering a question about a single day.

    kind: 'clock_in', 'clock_out', 'clock_both', or 'status'.
    """
    when = fmt_day(day)
    if row is None:
        return f"I couldn't find an attendance record for {when}."

    status = row.get("status")
    cin = fmt_clock(row.get("clock_in"), tz)
    cout = fmt_clock(row.get("clock_out"), tz)
    status_desc = status_text(status, row.get("work_location"))

    if kind == "clock_both":
        return (
            f"Your clock-in time on {when} was {cin or 'not recorded'}, "
            f"and your clock-out time was {cout or 'not recorded'}."
        )

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
    """Summary sentence for a month or range, without the day-by-day list."""
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
    by_day = _rows_by_day(rows)
    days = _days_in_range(start, end)
    if not rows and len(days) > EMPTY_DAY_LISTING_LIMIT:
        return f"I couldn't find any attendance records for {span}."

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
    """One line per day in the range with the clock-in, clock-out, or both times."""
    span = fmt_range(start, end)
    if kind == "clock_both":
        label = "clock-in and clock-out"
    elif kind == "clock_in":
        label = "clock-in"
    else:
        label = "clock-out"
    by_day = _rows_by_day(rows)
    days = _days_in_range(start, end)
    if not rows and len(days) > EMPTY_DAY_LISTING_LIMIT:
        return f"I couldn't find any attendance records for {span}."

    note = ""
    if len(days) > MAX_LIST_ROWS:
        days = sorted(by_day)
        note = f"Showing the {len(days)} days with records."

    lines = [f"Your {label} times for {span}:"]
    for day in days:
        row = by_day.get(day)
        if row is None:
            lines.append(f"- {_day_label(day)}: no attendance record")
        elif kind == "clock_both":
            cin = fmt_clock(row.get("clock_in"), tz) or "no clock-in"
            cout = fmt_clock(row.get("clock_out"), tz) or "no clock-out"
            lines.append(f"- {_day_label(day)}: In {cin} | Out {cout}")
        else:
            field = "clock_in" if kind == "clock_in" else "clock_out"
            value = fmt_clock(row.get(field), tz)
            lines.append(f"- {_day_label(day)}: {value or 'no ' + label + ' recorded'}")
    if note:
        lines.append(note)
    return "\n".join(lines)


def status_records_answer(rows: list[dict[str, Any]], span: str, label: str) -> str:
    """Summary of records with one status, e.g. late, with their dates."""
    if not rows:
        return f"You had no {label} records {span}.".replace("  ", " ")
    dates = sorted(d for d in (_row_date(r) for r in rows) if d)
    noun = f"{label} record" if len(rows) == 1 else f"{label} records"
    listed = ", ".join(_day_label(d) for d in dates)
    return f"You had {len(rows)} {noun} {span}: {listed}."


def status_list_answer(rows: list[dict[str, Any]], start: date, end: date, label: str, tz) -> str:
    """Only the records with one status, one line each. Days without a match are not shown."""
    span = fmt_range(start, end)
    if not rows:
        return f"I couldn't find any {label} records for {span}."
    lines = [f"Your {label} records for {span}:"]
    for row in sorted(rows, key=lambda r: _row_date(r) or date.min):
        day = _row_date(row)
        day_text = _day_label(day) if day else "Unknown date"
        cin = fmt_clock(row.get("clock_in"), tz) or "-"
        cout = fmt_clock(row.get("clock_out"), tz) or "-"
        lines.append(
            f"- {day_text}: {status_text(row.get('status'), row.get('work_location'))} "
            f"| In: {cin} | Out: {cout}"
        )
    return "\n".join(lines)