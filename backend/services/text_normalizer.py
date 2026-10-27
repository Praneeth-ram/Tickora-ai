"""Spelling correction for employee questions.
Only words close to a known word are changed, and only words the app understands are
used as targets. Names, numbers, and dates are left untouched.
"""
import difflib
import re
from backend.services.date_resolver import MONTHS

_DOMAIN_WORDS = {
    "attendance", "clock", "check", "punch", "status", "late", "absent", "present",
    "half", "day", "days", "leave", "leaves", "holiday", "holidays", "work", "working",
    "from", "home", "wfh", "reason", "applied", "apply", "applying", "application",
    "request", "requests", "requested", "submitted", "date", "dates", "month", "year",
    "balance", "timesheet", "timesheets", "hours", "overtime", "minutes", "worked",
    "upcoming", "coming", "next", "show", "list", "details", "detail", "count", "many",
    "total", "record", "records", "approved", "pending", "rejected", "cancelled",
    "available", "today", "yesterday", "week", "last", "this", "between", "what", "when",
    "which", "where", "much", "the", "and", "for", "are", "was", "were", "there", "have",
    "has", "did", "does", "you", "your", "with", "about", "casual", "sick", "earned",
    "unpaid", "maternity", "comp", "compoff", "off", "time", "in", "on", "of", "to", "at",
    "my", "me", "is", "it", "that", "can", "how", "long", "why","times", "attend", "attended", 
    "attending", "minute", "minutes", "hour",
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