"""Spelling correction for employee questions.
Only words close to a known word are changed, and only words the app understands are
used as targets. Names, numbers, and dates are left untouched.
"""
import difflib
import re
from backend.services.date_resolver import MONTHS

_DOMAIN_WORDS = {
    # Attendance / time
    "attendance", "clock", "check", "punch", "status", "late", "absent", "present",
    "half", "day", "days", "overtime", "minutes", "worked", "work", "working",
    "hours", "hour", "minute", "times", "attend", "attended", "attending",
    # Leave topics
    "leave", "leaves", "balance", "allocated", "remaining", "available", "used",
    "taken", "pending", "accrued", "entitled", "entitlement", "quota", "credit",
    "casual", "sick", "earned", "unpaid", "maternity", "paternity", "annual",
    "privilege", "bereavement", "carryover",
    # Leave type codes / shorthand
    "comp", "compoff", "off",
    # WFH / remote
    "wfh", "home", "remote",
    # Leave/WFH requests
    "holiday", "holidays", "request", "requests", "requested", "reason",
    "applied", "apply", "applying", "application", "approved", "rejected",
    "cancelled", "submitted",
    # Timesheet
    "timesheet", "timesheets",
    # Date words
    "date", "dates", "month", "year", "week", "today", "yesterday",
    "upcoming", "coming", "next", "last", "this", "between",
    # Query helpers
    "show", "list", "details", "detail", "count", "many", "total",
    "record", "records",
    # Common question words
    "what", "when", "which", "where", "much", "how", "long", "why", "can",
    # Articles / conjunctions / prepositions
    "the", "and", "for", "are", "was", "were", "there", "have", "has",
    "did", "does", "you", "your", "with", "about", "from", "in", "on",
    "of", "to", "at", "my", "me", "is", "it", "that",
}
_VOCABULARY = _DOMAIN_WORDS | set(MONTHS)
_WORD = re.compile(r"[A-Za-z]+")
_MIN_SIMILARITY = 0.8


def _best_match(word: str) -> str | None:
    best, best_score = None, 0.0
    for candidate in _VOCABULARY:
        if len(candidate) < 3:
            continue
        if sorted(candidate) == sorted(word):
            return candidate  # letters swapped, e.g. "wrok" -> "work"
        score = difflib.SequenceMatcher(None, word, candidate).ratio()
        if score > best_score:
            best, best_score = candidate, score
    return best if best_score >= _MIN_SIMILARITY else None


def correct_typos(question: str) -> str:
    """Correct misspelled words that are close to a known word. Other text is unchanged."""
    def fix(match: re.Match) -> str:
        word = match.group(0)
        lower = word.lower()
        if len(lower) < 4 or lower in _VOCABULARY:
            return word
        if any(lower.rstrip("s") == known.rstrip("s") for known in _VOCABULARY):
            return word  # plural or singular of a known word, e.g. "times"
        return _best_match(lower) or word
    return _WORD.sub(fix, question)