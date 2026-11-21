import json
import re
from backend.services.model_inference import generate_text

ANSWER_RULES = """\
You answer an HR question using only the FACTS (JSON).

Rules:
1. Write one complete sentence, or two at most. Never reply with bare numbers.
2. Answer the question that was asked.
3. Use only the values in FACTS. Do not add, subtract, or convert any value.
4. Use period_text exactly as given for the period.
5. If found is false, say no matching records were found for that period.
6. Refer to the user as "you".
7. Do not mention databases, queries, JSON, or the system.
8. The user is the person being described. Always say "you" or "your". Never say "employees".
9. For attendance counts, always say "days", never "instances", "times", or "records".
10. Never put a space before a comma or full stop.
11. Never say "days" for hours or minutes. Use "hours" and "minutes" only for time totals.
12. Use singular and plural correctly: "1 hour", "2 hours", "1 day", "2 days".
13. Do not use "I" as the subject. Use "you".
14. Never write "no", "none", or "zero" about a status whose count is above zero.
15. Never write minute totals in brackets or otherwise. When hours and minutes are given, use only hours and minutes.
16. Do not repeat the same figures in more than one sentence.
17. Write status words plainly, without quotation marks.
18. Express zero absences as "no absences", not "0 days of absence".
19. Never put a comma between a month and a year, for example "October, 2026".
"""

NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
PAREN_MINUTES_RE = re.compile(r"\([^)]*\b\d[\d,]*\s*minutes?\b[^)]*\)", re.IGNORECASE)
DAY_WORD_RE = re.compile(r"\bdays?\b", re.IGNORECASE)
MONTH_YEAR_COMMA_RE = re.compile(
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\s*\.?\s*,\s*\d{4}\b",
    re.IGNORECASE,
)

INSTANCE_RE = re.compile(r"\binstances?\b|\btimes\b", re.IGNORECASE)
QUOTED_LABEL_RE = re.compile(r"['\"](?:late|present|absent|half day)['\"]", re.IGNORECASE)
BARE_NUMBER_RE = re.compile(r"\b\d+\b(?!\s*(?:day|days|hour|hours|minute|minutes|leave|request|requests|record|records|%))")

def write_answer(question: str, payload: dict) -> str:
    facts = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    return generate_text(ANSWER_RULES, f"Question: {question}\nFACTS: {facts}", max_new_tokens=150).strip()

def _numbers(text: str) -> set[str]:
    out = set()
    for raw in NUMBER_RE.findall(text):
        value = float(raw)
        out.add(str(int(value)) if value.is_integer() else str(value))
    return out

NO_RECORDS_PHRASES = ("no matching records", "no records", "not found", "no attendance")

def _count(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0

def _positive_status_labels(facts: dict) -> list[str]:
    """Status labels the facts report with a count above zero."""
    labels: list[str] = []
    if facts.get("status") is not None and _count(facts.get("count")) > 0:
        labels.append(str(facts["status"]))
    for group in facts.get("groups") or []:
        if isinstance(group, dict) and group.get("label") is not None and _count(group.get("count")) > 0:
            labels.append(str(group["label"]))
    return labels

def _status_variants(label: str) -> set[str]:
    variants = {label}
    if label == "absent":
        variants.update({"absence", "absences"})
    variants.add(label + "s")
    return variants

def _has_negated_status(text: str, facts: dict) -> bool:
    for label in _positive_status_labels(facts):
        for variant in _status_variants(label):
            pattern = re.compile(
                rf"\b(?:no|none|zero)\s+{re.escape(variant)}\b",
                re.IGNORECASE,
            )
            if pattern.search(text):
                return True
    return False

def passes_answer_check(answer: str, facts: dict) -> bool:
    text = answer.lower()
    # Five words is the shortest complete answer ("You had 2 late days.").
    if not answer or len(answer.split()) < 5:
        return False
    if _has_negated_status(text, facts):
        return False
    if PAREN_MINUTES_RE.search(answer):
        return False
    if facts.get("measure") in {"worked time", "overtime"}:
        if DAY_WORD_RE.search(text) or "hour" not in text:
            return False
    if MONTH_YEAR_COMMA_RE.search(answer):
        return False
    if facts.get("found") and any(p in text for p in NO_RECORDS_PHRASES):
        return False
    if not _numbers(answer) <= _numbers(json.dumps(facts, default=str)):
        return False
    if INSTANCE_RE.search(text):
        return False
    if QUOTED_LABEL_RE.search(answer):
        return False
    if facts.get("groups") and BARE_NUMBER_RE.search(answer):
        return False
    return True
