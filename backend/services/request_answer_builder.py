"""Plain-language answers for leave, work-from-home, and holiday questions."""
import re
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any
from backend.services.answer_builder import MAX_LIST_ROWS, fmt_range

LEAVE_NOUNS = ("leave request", "leave requests")
WFH_NOUNS = ("work-from-home request", "work-from-home requests")

def as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None

def period_phrase(start: date | None, end: date | None) -> str:
    """'on 19 October 2026', 'in October 2026', 'in 2026', or 'from 1 to 15 October 2026'."""
    if start is None or end is None:
        return ""
    if start == end:
        return f"on {start.day} {start:%B %Y}"
    last = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    if start.day == 1 and end == last and start.month == end.month:
        return f"in {start:%B %Y}"
    if start.month == 1 and start.day == 1 and end.month == 12 and end.day == 31 and start.year == end.year:
        return f"in {start.year}"
    return f"from {fmt_range(start, end)}"

def requested_field(question: str) -> str | None:
    """Which detail of the request the user is asking about, if any."""
    q = question.lower()
    if re.search(r"\b(?:reason|why)\b", q):
        return "reason"
    if re.search(r"\b(?:appl(?:y|ied|ying|ication)|requested|submitted|submission)\b", q):
        return "applied"
    if re.search(r"\b(?:status|approved|pending|rejected|cancelled)\b", q):
        return "status"
    if re.search(r"\b(?:how\s+many\s+days|duration|how\s+long)\b", q):
        return "days"
    if re.search(r"\b(?:when|which\s+date|what\s+dates?)\b", q):
        return "period"
    return None

def _sort_key(row: dict[str, Any]) -> date:
    return (
        as_date(row.get("applied_at") or row.get("requested_at"))
        or as_date(row.get("start_date"))
        or date.min
    )

def _day_count(row: dict[str, Any]) -> int | None:
    if row.get("requested_days") is not None:
        return int(float(row["requested_days"]))
    start, end = as_date(row.get("start_date")), as_date(row.get("end_date"))
    if start and end:
        return (end - start).days + 1
    return None

def _field_sentence(row: dict[str, Any], field: str, singular: str, plural: str, count: int) -> str:
    start, end = as_date(row.get("start_date")), as_date(row.get("end_date"))
    dates = fmt_range(start, end) if start and end else "the dates on record"
    applied = as_date(row.get("applied_at") or row.get("requested_at"))
    status = (row.get("status") or "unknown").lower().replace("_", " ")
    reason = (row.get("reason") or "").strip()

    if field == "applied":
        if applied:
            tail = f"was applied for on {applied.day} {applied:%B %Y} and covers {dates}."
        else:
            tail = f"covers {dates}; no application date is recorded."
    elif field == "reason":
        tail = f"covers {dates} and has the reason: {reason}." if reason else f"covers {dates}; no reason was recorded."
    elif field == "status":
        tail = f"covers {dates} and is {status}."
    elif field == "days":
        days = _day_count(row)
        tail = f"covers {dates}, which is {days} day{'s' if days != 1 else ''}." if days else f"covers {dates}."
    else:
        tail = f"covers {dates}."

    if count == 1:
        return f"Your {singular} {tail}"
    return f"You have {count} {plural}. The most recent one {tail}"

def _summary_sentence(rows: list[dict[str, Any]], singular: str, plural: str, span: str) -> str:
    counts = Counter((row.get("status") or "unknown").lower().replace("_", " ") for row in rows)
    parts = ", ".join(f"{n} {status}" for status, n in counts.most_common())
    noun = singular if len(rows) == 1 else plural
    where = f" {span}" if span else ""
    return (
        f"You have {len(rows)} {noun}{where}: {parts}. "
        "Ask about the reason, applied date, or status of a specific request to see its details."
    )

def _list_block(rows: list[dict[str, Any]], plural: str, span: str) -> str:
    shown = rows[:MAX_LIST_ROWS]
    where = f" {span}" if span else ""
    lines = [f"Your {plural}{where}:"]
    for row in shown:
        start, end = as_date(row.get("start_date")), as_date(row.get("end_date"))
        dates = fmt_range(start, end) if start and end else "dates not recorded"
        status = (row.get("status") or "unknown").lower().replace("_", " ")
        applied = as_date(row.get("applied_at") or row.get("requested_at"))
        applied_text = f", applied {applied.day} {applied:%b %Y}" if applied else ""
        lines.append(f"- {dates}: {status}{applied_text}")
    if len(rows) > len(shown):
        lines.append(f"Showing {len(shown)} of {len(rows)} requests.")
    return "\n".join(lines)

def request_answer(
    kind: str,
    rows: list[dict[str, Any]],
    question: str,
    span: str,
    wants_list: bool,
) -> str:
    """Answer a leave ('leave') or work-from-home ('wfh') question."""
    singular, plural = LEAVE_NOUNS if kind == "leave" else WFH_NOUNS
    if not rows:
        where = f" {span}" if span else " on record"
        return f"You have no {plural}{where}."

    ordered = sorted(rows, key=_sort_key, reverse=True)
    if wants_list:
        return _list_block(ordered, plural, span)

    field = requested_field(question)
    if field is None:
        return _summary_sentence(ordered, singular, plural, span)
    return _field_sentence(ordered[0], field, singular, plural, len(ordered))

def holiday_answer(
    rows: list[dict[str, Any]],
    start: date | None,
    end: date | None,
    wants_list: bool,
    is_upcoming: bool = False,
) -> str:
    """Answer a holiday question with one sentence, or a list when the user asks for it."""
    span = period_phrase(start, end)
    items = []
    for row in rows:
        name = (row.get("holiday_name") or row.get("name") or "Holiday").strip()
        items.append((as_date(row.get("holiday_date")), name))
    items.sort(key=lambda item: item[0] or date.min)

    if not items:
        if is_upcoming:
            if start and end and start.year == end.year:
                return f"There are no upcoming holidays in {end.year}."
            return "There are no upcoming holidays for the requested period."
        return f"There are no holidays {span}." if span else "There are no holidays for the period you asked about."

    def label(day: date | None, name: str) -> str:
        if day is None:
            return name
        return f"{name} ({day.strftime('%A')}, {day.day} {day.strftime('%B %Y')})"

    count = len(items)
    noun = "upcoming holiday" if is_upcoming else "holiday"
    noun = noun if count == 1 else f"{noun}s"
    verb = "is" if count == 1 else "are"

    if is_upcoming and start and end and start.year == end.year:
        lead = f"There {verb} {count} {noun} in {end.year}"
    else:
        lead = f"There {verb} {count} {noun}" + (f" {span}" if span else "")

    if wants_list:
        lines = [f"{lead}:"] + [f"- {label(day, name)}" for day, name in items[:MAX_LIST_ROWS]]
        if count > MAX_LIST_ROWS:
            lines.append(f"Showing {MAX_LIST_ROWS} of {count} holidays.")
        return "\n".join(lines)

    shown = items[:10]
    body = "; ".join(label(day, name) for day, name in shown)
    extra = f", and {count - 10} more" if count > 10 else ""
    return f"{lead}: {body}{extra}."

STATUS_VERB = {"approved": "was", "rejected": "was", "cancelled": "was", "pending": "is"}

def status_check_answer(kind: str, rows: list[dict[str, Any]], target: str, span: str) -> str:
    """Answer 'was my leave approved?' style questions with Yes or No first."""
    singular, plural = LEAVE_NOUNS if kind == "leave" else WFH_NOUNS
    scope = f" {span}" if span else ""
    if not rows:
        return f"No, you have no {plural}{scope if span else ' on record'}."

    ordered = sorted(rows, key=_sort_key, reverse=True)
    latest = ordered[0]
    start, end = as_date(latest.get("start_date")), as_date(latest.get("end_date"))
    dates = fmt_range(start, end) if start and end else "the dates on record"
    actual = (latest.get("status") or "unknown").lower().replace("_", " ")
    verb = STATUS_VERB.get(target, "is")
    matches = [row for row in ordered if (row.get("status") or "").lower() == target]

    if len(ordered) == 1:
        if matches:
            return f"Yes, your {singular} for {dates} {verb} {target}."
        return f"No, your {singular} for {dates} is {actual}."

    count = len(matches)
    if count:
        return f"Yes, {count} of your {plural}{scope} {'was' if count == 1 else 'were'} {target}."
    return (
        f"No, none of your {plural}{scope} {'was' if len(ordered) == 1 else 'were'} {target}. "
        f"Your most recent one for {dates} is {actual}."
    )