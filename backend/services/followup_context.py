"""Reuse the period of the previous answer for short follow-up questions, for any entity."""
import re
from datetime import date
from typing import Any

from backend.services.date_resolver import resolve_date_spec

FOLLOWUP_START_RE = re.compile(
    r"^\s*(?:and|also|what\s+about|how\s+about|same|for|then)\b", re.IGNORECASE
)
STANDALONE_OPENER_RE = re.compile(
    r"^\s*(?:show|list|display|give\s+me|get|tell\s+me)\b", re.IGNORECASE
)
MAX_FOLLOWUP_WORDS = 6

FIELD_PATTERNS = {
    "clock in": r"\bclock[- ]?in\b|\bcheck[- ]?in\b|\bpunch[- ]?in\b",
    "clock out": r"\bclock[- ]?out\b|\bcheck[- ]?out\b|\bpunch[- ]?out\b",
    "work location": r"\bwork(?:ing)?\s+location\b|\bwhere\s+did\s+i\s+work\b",
    "worked time": r"\bworked\s+time\b|\bhours?\s+(?:did\s+i\s+)?work(?:ed)?\b",
    "overtime": r"\bovertime\b",
    "status": r"\bstatus\b",
}

def flatten_fields(value) -> list[str]:
    """Return a flat list of field names, whatever nesting the value arrived with."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    flat: list[str] = []
    for item in value:
        flat.extend(flatten_fields(item))
    return flat

def requested_fields(question: str) -> list[str]:
    """Return the field names the question asks about, e.g. ['clock in']."""
    return [label for label, pattern in FIELD_PATTERNS.items()
            if re.search(pattern, question, re.IGNORECASE)]

def is_followup_question(question: str) -> bool:
    words = re.findall(r"[A-Za-z']+", question)
    return bool(FOLLOWUP_START_RE.search(question)) or len(words) <= MAX_FOLLOWUP_WORDS

def inherit_fields(question: str, last_context: dict | None, operation_id: str | None) -> list[str]:
    fields = flatten_fields(requested_fields(question))
    if fields or not last_context or not operation_id:
        return fields
    if last_context.get("operation_id") != operation_id:
        return fields
    if not is_followup_question(question):
        return fields
    return flatten_fields(last_context.get("fields"))

def _same_type(sample: Any, value: date) -> Any:
    """Return the date in the same type the rest of the pipeline uses (string or date)."""
    return value.isoformat() if isinstance(sample, str) else value

def apply_context_period(
    question: str,
    period: dict,
    last_context: dict | None,
    has_explicit_date: bool,
    operation_id: str | None = None,
) -> tuple[dict, bool]:
    """Return (period, reused). Reuse only for date-less follow-up questions."""
    if has_explicit_date or not last_context:
        return period, False
    if resolve_date_spec(question, date.today()) is not None:
        return period, False
    if operation_id is not None:
        last_op = str(last_context.get("operation_id") or "")
        if last_op.partition(".")[0] != operation_id.partition(".")[0]:
            return period, False
    if STANDALONE_OPENER_RE.search(question) and not FOLLOWUP_START_RE.search(question):
        return period, False
    start = last_context.get("start_date")
    end = last_context.get("end_date")
    if not start or not end:
        return period, False

    words = re.findall(r"[A-Za-z']+", question)
    is_followup = bool(FOLLOWUP_START_RE.search(question)) or len(words) <= MAX_FOLLOWUP_WORDS
    if not is_followup:
        return period, False

    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    sample = period.get("start_date", start)
    reused_period = {**period,
                     "start_date": _same_type(sample, start_date),
                     "end_date": _same_type(period.get("end_date", end), end_date)}
    return reused_period, True