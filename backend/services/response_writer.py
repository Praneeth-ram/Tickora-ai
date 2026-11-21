"""Plain-language answers from a validated payload.

The responder receives a payload the builders already approved. An answer is
used only if it passes three checks: every number appears in the payload or
the draft, it is one or two full sentences addressed to the user, and it
states the year of the period. Otherwise the template answer is returned.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
PERSONAL_RE = re.compile(r"\b(?:you|your)\b", re.IGNORECASE)
SENTENCE_END_RE = re.compile(r"[.!?](?=\s|$)")

RESPONSE_RULES = """\
You write the final answer to an HR question. You receive the question, FACTS (JSON), and a DRAFT answer.

Rules:
1. Use only numbers, dates, and labels that appear in FACTS or DRAFT.
2. Do not add, estimate, or infer any figure.
3. If result.count is 0, say that no matching records were found in the period.
4. If truncated is true, say how many rows are shown out of the total.
5. Always state the period using period.label, including its year.
6. Use "days" for attendance counts, and "hours" and "minutes" for time totals.
7. Write one or two complete sentences addressed to the user as "you".
8. Do not write lists, labels with colons, or fragments.
9. Do not mention databases, queries, plans, JSON, or the system.
"""

MAX_NEW_TOKENS = 150

MONTH_YEAR_RE = re.compile(
    r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4}\b",
    re.IGNORECASE,
)

def check_period(candidate: str, draft: str) -> bool:
    expected = {m.lower() for m in MONTH_YEAR_RE.findall(draft)}
    return all(p in candidate.lower() for p in expected)

QUALIFIERS = ("so far", "no ", "not ", "absent", "late", "present", "half", "overtime", "worked")

def check_qualifiers(candidate: str, draft: str) -> bool:
    cand, base = candidate.lower(), draft.lower()
    return all(q in cand for q in QUALIFIERS if q in base)

def _numbers(text: str) -> set[str]:
    """Normalise numbers so that '9', '9.0' and '09' compare equal."""
    out = set()
    for raw in NUMBER_RE.findall(text):
        value = float(raw)
        out.add(str(int(value)) if value.is_integer() else str(value))
    return out


def check_numbers(candidate: str, facts: str, draft: str) -> bool:
    """True only if the candidate uses no number that the facts or draft lack."""
    if not candidate or not candidate.strip():
        return False
    return _numbers(candidate) <= (_numbers(facts) | _numbers(draft))


def check_guards(candidate: str, payload: dict[str, Any]) -> bool:
    """Deterministic checks the prompt cannot guarantee."""
    text = candidate.strip()
    sentences = [s for s in SENTENCE_END_RE.split(text) if s.strip()]
    if not 1 <= len(sentences) <= 2:
        return False
    if len(text.split()) < 5 or not PERSONAL_RE.search(text):
        return False
    label = (payload.get("period") or {}).get("label", "")
    years = set(YEAR_RE.findall(label))
    if years and not any(year in text for year in years):
        return False
    return True


def narrate(question: str, payload: dict[str, Any], draft: str, generate=None) -> str:
    """Return a narrated answer, or the draft when narration is skipped or fails.

    `generate` is injected for tests; in production it is model_inference.generate_text.
    """
    if payload.get("error") or not draft:
        return draft

    if generate is None:
        from backend.services.model_inference import generate_text as generate

    facts = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    try:
        candidate = generate(
            RESPONSE_RULES,
            f"Question: {question}\nFACTS: {facts}\nDRAFT: {draft}",
            max_new_tokens=MAX_NEW_TOKENS,
        ).strip()
    except Exception:
        logger.exception("Narration failed; using template answer")
        return draft

    if not check_numbers(candidate, facts, draft):
        logger.info("Narration rejected: number check")
        return draft
    if not check_guards(candidate, payload):
        logger.info("Narration rejected: sentence, voice, or period check")
        return draft

    if not check_qualifiers(candidate, draft):
        logger.info("Narration rejected: qualifier check")
        return draft

    if not check_period(candidate, draft):
        logger.info("Narration rejected: period check")
        return draft
    
    return candidate