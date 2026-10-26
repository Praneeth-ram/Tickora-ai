"""Deterministic date resolution for employee questions.

Every date in a question is resolved here, in code, never by the language model.
Rules are ordered from most specific to least specific so that a phrase such as
"19 oct 2026" resolves to one day, not to the whole month.
"""

import re
from dataclasses import dataclass
from datetime import date, timedelta

MONTHS: dict[str, int] = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}
# Longest names first so "september" wins over "sep".
_MON = "|".join(sorted(MONTHS, key=len, reverse=True))
_TO = r"(?:\s+(?:to|through|thru|till|until|and)\s+|\s*-\s*)"
_DAY = r"(\d{1,2})(?:st|nd|rd|th)?(?!\d)"
_YEAR_OPT = r"(?:,?\s*(\d{4}))?"


class InvalidDateError(ValueError):
    """Raised when a question names a date that does not exist, such as 31 February."""


@dataclass(frozen=True)
class DateSpec:
    start: date
    end: date
    kind: str  # "day", "range", "week", "month", "year", "relative"

    @property
    def is_single_day(self) -> bool:
        return self.start == self.end


def _valid(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _valid_iso(text: str) -> date | None:
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    nxt = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, nxt - timedelta(days=1)


def _month_number(word: str) -> int:
    return MONTHS[word.lower().rstrip(".")]


def _ordered_or_none(a: date | None, b: date | None):
    if a is None or b is None or a > b:
        return None
    return a, b


def resolve_date_spec(question: str, today: date) -> DateSpec | None:
    """Return the date span a question refers to, or None if it names no date."""
    q = " ".join(question.lower().split())

    # 1. ISO dates: 2026-10-19 and 2026-10-01 to 2026-10-15
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})" + _TO + r"(\d{4}-\d{2}-\d{2})\b", q)
    if m:
        span = _ordered_or_none(_valid_iso(m.group(1)), _valid_iso(m.group(2)))
        if span:
            return DateSpec(span[0], span[1], "range")
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", q)
    if m:
        d = _valid_iso(m.group(1))
        if d:
            return DateSpec(d, d, "day")

    # 2. Numeric day-first dates: 19/10/2026, 19-10-2026, 19.10.2026
    numeric = r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})"
    m = re.search(numeric + _TO + numeric, q)
    if m:
        s = _valid(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        e = _valid(int(m.group(6)), int(m.group(5)), int(m.group(4)))
        span = _ordered_or_none(s, e)
        if span:
            return DateSpec(span[0], span[1], "range")
    m = re.search(r"\b" + numeric + r"\b", q)
    if m:
        d = _valid(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        if d is None:
            raise InvalidDateError(m.group(0))
        return DateSpec(d, d, "day")

    # 3. Month-first date ranges: "june 1 to june 5", "june 1 to 5", "from june 1 to 5 2026", "june 28 to july 4"
    m = re.search(
        rf"\b({_MON})\.?\s+{_DAY}(?:,?\s*(\d{{4}}))?{_TO}(?:({_MON})\.?\s+)?{_DAY}(?:,?\s*(\d{{4}}))?\b",
        q,
    )
    if m:
        m1, d1, yr1, m2, d2, yr2 = m.groups()
        mo1 = _month_number(m1)
        mo2 = _month_number(m2) if m2 else mo1
        y2 = int(yr2) if yr2 else (int(yr1) if yr1 else today.year)
        y1 = int(yr1) if yr1 else y2
        if mo2 < mo1 and not yr1 and not yr2:
            y2 += 1
        span = _ordered_or_none(_valid(y1, mo1, int(d1)), _valid(y2, mo2, int(d2)))
        if span:
            return DateSpec(span[0], span[1], "range")

    # 4. Day-first date ranges: "1 to 15 oct 2026", "1 oct to 15 oct 2026", "1 oct 2026 to 15 oct 2026", "28 june to 4 july"
    m = re.search(
        rf"\b{_DAY}\s*(?:of\s+)?(?:({_MON})\.?(?:,?\s*(\d{{4}}))?\s*)?{_TO}{_DAY}\s*(?:of\s+)?({_MON})\.?(?:,?\s*(\d{{4}}))?\b",
        q,
    )
    if m:
        d1, m1, yr1, d2, m2, yr2 = m.groups()
        mo2 = _month_number(m2)
        mo1 = _month_number(m1) if m1 else mo2
        y2 = int(yr2) if yr2 else (int(yr1) if yr1 else today.year)
        y1 = int(yr1) if yr1 else y2
        if mo2 < mo1 and not yr1 and not yr2:
            y2 += 1
        span = _ordered_or_none(_valid(y1, mo1, int(d1)), _valid(y2, mo2, int(d2)))
        if span:
            return DateSpec(span[0], span[1], "range")

    # 5. Month-to-month ranges: "june to august", "from june to august 2026", "between june and august"
    m = re.search(
        rf"\b(?:from\s+|between\s+)?({_MON})\.?(?:,?\s*(\d{{4}}))?{_TO}({_MON})\.?(?:,?\s*(\d{{4}}))?\b",
        q,
    )
    if m:
        m1, yr1, m2, yr2 = m.groups()
        mo1 = _month_number(m1)
        mo2 = _month_number(m2)
        y2 = int(yr2) if yr2 else (int(yr1) if yr1 else today.year)
        y1 = int(yr1) if yr1 else y2
        if mo2 < mo1 and not yr1 and not yr2:
            y2 += 1
        s = date(y1, mo1, 1)
        e = _month_bounds(y2, mo2)[1]
        span = _ordered_or_none(s, e)
        if span:
            return DateSpec(span[0], span[1], "range")

    # 4. Single day with month name, either order: "19 oct 2026", "oct 19", "october 19th, 2026"
    m = re.search(rf"\b{_DAY}\s*(?:of\s+)?({_MON})\.?{_YEAR_OPT}", q)
    if m:
        year = int(m.group(3)) if m.group(3) else today.year
        d = _valid(year, _month_number(m.group(2)), int(m.group(1)))
        if d is None:
            raise InvalidDateError(m.group(0))
        return DateSpec(d, d, "day")
    m = re.search(rf"\b({_MON})\.?\s+{_DAY}{_YEAR_OPT}", q)
    if m:
        year = int(m.group(3)) if m.group(3) else today.year
        d = _valid(year, _month_number(m.group(1)), int(m.group(2)))
        if d is None:
            raise InvalidDateError(m.group(0))
        return DateSpec(d, d, "day")

    # 5. Relative phrases
    if re.search(r"\btoday\b", q):
        return DateSpec(today, today, "relative")
    if re.search(r"\byesterday\b", q):
        y = today - timedelta(days=1)
        return DateSpec(y, y, "relative")
    if re.search(r"\bthis\s+week\b", q):
        s = today - timedelta(days=today.weekday())
        return DateSpec(s, s + timedelta(days=6), "week")
    if re.search(r"\blast\s+week\b", q):
        s = today - timedelta(days=today.weekday() + 7)
        return DateSpec(s, s + timedelta(days=6), "week")
    if re.search(r"\bthis\s+month\b", q):
        s, e = _month_bounds(today.year, today.month)
        return DateSpec(s, e, "month")
    if re.search(r"\blast\s+month\b", q):
        prev = today.replace(day=1) - timedelta(days=1)
        s, e = _month_bounds(prev.year, prev.month)
        return DateSpec(s, e, "month")
    if re.search(r"\b(?:this|current)\s+year\b", q):
        return DateSpec(date(today.year, 1, 1), date(today.year, 12, 31), "year")
    if re.search(r"\blast\s+year\b", q):
        y = today.year - 1
        return DateSpec(date(y, 1, 1), date(y, 12, 31), "year")

    # 6. Month name with optional year: "october 2026", "in october", "oct 2026"
    for m in re.finditer(rf"\b({_MON})\.?(?:,?\s*(\d{{4}}))?\b", q):
        word = m.group(1)
        # "may" is also an ordinary word: only a month with a year or after in/of/for.
        if word == "may" and not m.group(2) and not re.search(r"\b(?:in|of|for|during)\s+may\b", q):
            continue
        year = int(m.group(2)) if m.group(2) else today.year
        s, e = _month_bounds(year, _month_number(word))
        return DateSpec(s, e, "month")

    # 7. Bare year: "2026"
    m = re.search(r"\b(20\d\d)\b", q)
    if m:
        y = int(m.group(1))
        return DateSpec(date(y, 1, 1), date(y, 12, 31), "year")

    return None