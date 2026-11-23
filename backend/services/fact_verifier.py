"""Generic answer verifier.
Every number, unit, status, period and name in an LLM answer must be supported
by the FACTS payload. The check reads the facts, not the sentence shape, so it
works for any entity and any question without a new pattern per question.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

TOKEN_RE = re.compile(
    r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|[A-Za-z][A-Za-z'-]*|[.,;:!?]"
)
WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")
NUMBER_RE = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")

# Grammar and neutral words. These carry no facts, so they are always allowed.
FUNCTION_WORDS = {
    "a", "an", "the", "and", "or", "of", "in", "on", "at", "to", "for", "from",
    "by", "with", "as", "that", "this", "it", "its", "there", "here", "you",
    "your", "be", "is", "are", "was", "were", "been", "have", "has", "had",
    "not", "found", "total", "remaining", "shown", "so", "far", "were",
    "worked", "work", "did", "do", "does", "also", "only", "per", "during",
    "between", "through", "until", "since", "what", "which", "who", "when",
    "they", "them", "their", "we", "our", "no", "none", "zero", "nothing",
}
# Time words are always allowed; they describe the unit of a time total.
TIME_WORDS = {"hour", "hours", "minute", "minutes", "time", "am", "pm"}
NEGATIONS = {"no", "none", "zero", "nothing"}
BE_VERBS = {"was", "is", "were", "are"}
SINGULAR_BE = {"was", "is"}
PLURAL_BE = {"were", "are"}
NUMBER_WORDS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
    "eleven": "11", "twelve": "12",
}
STRUCTURAL_KEYS = {
    "shape", "entity", "unit", "unit_singular", "period_text", "filters",
    "found", "total", "truncated", "rows", "groups", "count", "status",
    "measure", "hours", "minutes", "label", "amounts", "currency", "value",
    "field", "metrics", "record",
}
MONTH_NAMES = {
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
}

def _norm(text: str) -> str:
    """Normalize a number so 64680.00, 64,680 and 64680 compare equal."""
    try:
        return format(Decimal(text.replace(",", "")).normalize(), "f")
    except InvalidOperation:
        return text


def _walk(value: Any, words: set[str], numbers: set[str]) -> None:
    """Collect words and numbers from fact values. Dict keys are not collected."""
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if key not in STRUCTURAL_KEYS:
                words.update(WORD_RE.findall(key.lower()))
            _walk(item, words, numbers)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            _walk(item, words, numbers)
    elif isinstance(value, (int, float, Decimal)):
        numbers.add(_norm(str(value)))
    elif isinstance(value, str):
        for token in NUMBER_RE.findall(value):
            numbers.add(_norm(token))
        for word in WORD_RE.findall(value):
            words.add(word.lower())


def _with_forms(words: set[str]) -> set[str]:
    """Add the singular and plural form of each word, so 'late' also allows 'lates'."""
    forms = set(words)
    for word in words:
        if word.endswith("s") and len(word) > 3:
            forms.add(word[:-1])
        else:
            forms.add(word + "s")
    return forms


def _is_year(token: str) -> bool:
    return token.isdigit() and len(token) == 4 and 1900 <= int(token) <= 2100


def _count(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _positive_labels(facts: dict) -> set[str]:
    """Single-word status labels the facts report with a count above zero."""
    labels: set[str] = set()
    if facts.get("status") and _count(facts.get("count")) > 0:
        labels.add(str(facts["status"]).lower())
    for group in facts.get("groups") or []:
        if isinstance(group, dict) and group.get("label") and _count(group.get("count")) > 0:
            labels.add(str(group["label"]).lower())
    return {label for label in labels if " " not in label and "_" not in label}


def verify_against_facts(answer: str, facts: dict) -> str | None:
    """Return the name of the first failed check, or None when every claim is supported."""
    if not answer or len(answer.split()) < 3:
        return "too_short"

    tokens = TOKEN_RE.findall(answer)
    if "I" in tokens:
        return "first_person_I"
    if "0" in tokens:
        return "zero_digit"

    lowered = answer.lower().replace("-", " ")
    for field in facts.get("requested_fields") or []:
        if field.lower().replace("-", " ") not in lowered:
            return f"requested_field_missing:{field}"

    words: set[str] = set()
    numbers: set[str] = set()
    _walk(facts, words, numbers)
    vocab = _with_forms(words) | FUNCTION_WORDS | TIME_WORDS

    unit = str(facts.get("unit") or "").lower().split()
    singular = str(facts.get("unit_singular") or "").lower().split()
    unit_last = unit[-1] if unit else ""
    singular_last = singular[-1] if singular else ""
    positive = _positive_labels(facts)
    time_measure = facts.get("measure") in {"worked time", "overtime"}

    for index, token in enumerate(tokens):
        lower = token.lower()

        if token[0].isdigit():
            if _is_year(token):
                continue
            if _norm(token.replace(",", "")) not in numbers:
                return "number_not_in_facts"
            count = int(token) if token.isdigit() else None
            following = [t.lower() for t in tokens[index + 1:index + 4] if t[0].isalpha()]
            if count is not None:
                # Unit agreement: "1 day" and "2 days", within the next two words.
                for word in following[:2]:
                    if count == 1 and unit_last and word == unit_last and unit_last != singular_last:
                        return "unit_plural_for_one"
                    if count != 1 and singular_last and word == singular_last and unit_last != singular_last:
                        return "unit_singular_for_many"
                # Verb agreement: "1 task was", "2 days were", within the next three words.
                for word in following[:3]:
                    if word in MONTH_NAMES:
                        break
                    if word in BE_VERBS:
                        if count == 1 and word in PLURAL_BE:
                            return "verb_plural_for_one"
                        if count != 1 and word in SINGULAR_BE:
                            return "verb_singular_for_many"
                        break
            continue

        if not token[0].isalpha():
            continue

        if lower in NEGATIONS:
            nearby = [t.lower() for t in tokens[index + 1:index + 5] if t[0].isalpha()]
            if any(word in positive for word in nearby):
                return "negated_positive_status"

        if time_measure and lower in {"day", "days"}:
            return "day_word_for_time_total"

        if lower in NUMBER_WORDS:
            if NUMBER_WORDS[lower] not in numbers:
                return "spelled_number_not_in_facts"
            continue

        if lower not in vocab:
            return f"unsupported_word:{lower}"

    return None