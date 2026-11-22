import json
import re
from backend.services.model_inference import generate_text

UNIT_RULE = (
    'Use the unit from FACTS exactly. For leave requests write "leave requests". '
    'For attendance adjustments write "attendance adjustments". For clock punches '
    'write "clock punches". Never write "records" or "on record".'
)

ANSWER_RULES = """\
You answer an HR question using only the FACTS (JSON).

Rules:
1. Write one complete sentence, or two at most. Never reply with bare numbers.
2. Answer the question that was asked.
3. Use only the values in FACTS. Do not add, subtract, or convert any value.
4. Use period_text exactly as given for the period.
5. If found is false, say no matching items were found for period_text. Use the entity's unit from FACTS.
6. Refer to the user as "you".
7. Do not mention databases, queries, JSON, or the system.
8. The user is the person being described. Always say "you" or "your". Never say "employees".
9. Use unit_singular and unit from FACTS for singular and plural counts. Do not call another entity's items attendance days.
10. Never put a space before a comma or full stop.
11. Never say "days" for hours or minutes. Use "hours" and "minutes" only for time totals.
12. Use singular and plural correctly: "1 hour", "2 hours", "1 day", "2 days".
13. Do not use "I" as the subject. Use "you".
14. Never write "no", "none", or "zero" about a status whose count is above zero.
15. Never write minute totals in brackets or otherwise. When hours and minutes are given, use only hours and minutes.
16. Do not repeat the same figures in more than one sentence.
17. Write status words plainly, without quotation marks.
18. For zero half-day attendance, say "no half day attendance records were found". For absent-day counts, say "no absent days were found".
19. Write the month and year together with no comma, for example "October 2026". Never write "October, 2026".
20. Use period_text exactly as given. Do not put "this", "last", or "next" before it.
21. Name the period from period_text. Never write "the specified period", "the requested period", or "the period".
22. For attendance, mention only statuses present in FACTS. Do not add a different attendance status.
23. For payroll, reproduce each amount and currency code exactly as shown in FACTS. Do not round, convert, calculate, or add another amount.
24. If FACTS lists more than one metric, state every metric in FACTS. Never leave one out.
"""

NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
PAREN_MINUTES_RE = re.compile(r"\([^)]*\b\d[\d,]*\s*minutes?\b[^)]*\)", re.IGNORECASE)
DAY_WORD_RE = re.compile(r"\bdays?\b", re.IGNORECASE)
MONTH_NAME_RE = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)"
)
MONTH_YEAR_RE = re.compile(
    rf"\b{MONTH_NAME_RE}(?:\s+|\.?\s*,\s*)\d{{4}}\b",
    re.IGNORECASE,
)
MONTH_YEAR_COMMA_RE = re.compile(
    rf"\b{MONTH_NAME_RE}\b.*?,.*?\b\d{{4}}\b",
    re.IGNORECASE | re.DOTALL,
)
RELATIVE_MONTH_RE = re.compile(
    rf"\b(?:this|last|next)\s+{MONTH_NAME_RE}\b",
    re.IGNORECASE,
)
REPEATED_UNIT_RE = re.compile(
    r"\b(day|hour|minute)s?\s+\1s?\b",
    re.IGNORECASE,
)
NUMBERED_UNIT_RE = re.compile(
    r"(?<![\w,])(\d+(?:,\d{3})*(?:\.\d+)?)\s+(days?|hours?|minutes?)\b",
    re.IGNORECASE,
)
INSTANCE_RE = re.compile(r"\binstances?\b|\btimes\b", re.IGNORECASE)
QUOTED_LABEL_RE = re.compile(r"['\"](?:late|present|absent|half day)['\"]", re.IGNORECASE)
BARE_NUMBER_RE = re.compile(r"\b\d+\b(?!\s*(?:day|days|hour|hours|minute|minutes|leave|request|requests|record|records|%))")
ON_RECORD_RE = re.compile(r"\bon record\b", re.IGNORECASE)
RECORDS_WORD_RE = re.compile(r"\brecords?\b", re.IGNORECASE)
STATUS_ATTENDANCE_RE = re.compile(
    r"\b(?:late|present|absent|half day)\s+attendance\b", re.IGNORECASE
)

MONTHS = (
    "January|February|March|April|May|June|July|August|"
    "September|October|November|December"
)
MONTH_YEAR_COMMA_RE = re.compile(rf"\b({MONTHS})(?:,\s*\1)?,\s*(\d{{4}})\b")


def normalize_answer(answer: str) -> str:
    """Remove the comma between month and year, and a repeated month.

    "October, 2026" -> "October 2026"
    "October, October, 2026" -> "October 2026"
    """
    return MONTH_YEAR_COMMA_RE.sub(r"\1 \2", answer)

def write_answer(question: str, payload: dict) -> str:
    facts = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    return generate_text(ANSWER_RULES, f"Question: {question}\nFACTS: {facts}", max_new_tokens=150).strip()

def _numbers(text: str) -> set[str]:
    out = set()
    text = MONTH_YEAR_RE.sub("", text)
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


def _has_invalid_unit_grammar(text: str) -> bool:
    if REPEATED_UNIT_RE.search(text):
        return True
    for match in NUMBERED_UNIT_RE.finditer(text):
        value = float(match.group(1).replace(",", ""))
        is_plural = match.group(2).lower().endswith("s")
        if (value == 1 and is_plural) or (value != 1 and not is_plural):
            return True
    return False


def _has_invalid_count_unit(text: str, facts: dict) -> bool:
    count = facts.get("count")
    singular = facts.get("unit_singular")
    plural = facts.get("unit")
    if not isinstance(count, int) or isinstance(count, bool):
        return False
    if not isinstance(singular, str) or not isinstance(plural, str) or singular == plural:
        return False

    def phrase_pattern(value: str) -> str:
        return r"[- ]+".join(
            re.escape(part) for part in re.split(r"[\s-]+", value)
        )

    pattern = re.compile(
        rf"\b{count}\s+(?:(?:[\w-]+\s+){{0,2}})?"
        rf"(?:(?P<singular>{phrase_pattern(singular)})|"
        rf"(?P<plural>{phrase_pattern(plural)}))\b",
        re.IGNORECASE,
    )
    expected_group = "singular" if count == 1 else "plural"
    return any(
        match.group(expected_group) is None
        for match in pattern.finditer(text)
    )


ATTENDANCE_STATUS_PATTERNS = {
    "present": re.compile(r"\bpresent\b", re.IGNORECASE),
    "late": re.compile(r"\blate\b", re.IGNORECASE),
    "absent": re.compile(r"\b(?:absent|absences?)\b", re.IGNORECASE),
    "half_day": re.compile(r"\bhalf[- ]days?\b", re.IGNORECASE),
    "on_leave": re.compile(r"\bon leave\b", re.IGNORECASE),
    "work_from_home": re.compile(r"\bwork[- ]from[- ]home\b|\bwfh\b", re.IGNORECASE),
}


def _attendance_status(value: object) -> str:
    normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {"absence": "absent", "absences": "absent"}
    return aliases.get(normalized, normalized)


def _has_unfounded_attendance_status(text: str, facts: dict) -> bool:
    if str(facts.get("entity", "")).lower() != "attendance":
        return False

    allowed: set[str] = set()
    if facts.get("status") is not None:
        allowed.add(_attendance_status(facts["status"]))
    for group in facts.get("groups") or []:
        if isinstance(group, dict) and group.get("label") is not None:
            allowed.add(_attendance_status(group["label"]))
    record = facts.get("record")
    if isinstance(record, dict) and record.get("status") is not None:
        allowed.add(_attendance_status(record["status"]))
    for row in facts.get("rows") or []:
        if isinstance(row, dict) and row.get("status") is not None:
            allowed.add(_attendance_status(row["status"]))

    return any(
        status not in allowed and pattern.search(text)
        for status, pattern in ATTENDANCE_STATUS_PATTERNS.items()
    )


def passes_answer_check(answer: str, facts: dict) -> bool:
    text = answer.lower()
    # Five words is the shortest complete answer ("You had 2 late days.").
    if not answer or len(answer.split()) < 5:
        return False
    if _has_negated_status(text, facts):
        return False
    if _has_unfounded_attendance_status(answer, facts):
        return False
    if _has_invalid_unit_grammar(answer):
        return False
    if _has_invalid_count_unit(answer, facts):
        return False
    if PAREN_MINUTES_RE.search(answer):
        return False
    if facts.get("measure") in {"worked time", "overtime"}:
        if DAY_WORD_RE.search(text) or "hour" not in text:
            return False
    if MONTH_YEAR_COMMA_RE.search(answer):
        return False
    if RELATIVE_MONTH_RE.search(answer):
        return False
    months = [match.group().lower()[:3] for match in re.finditer(MONTH_NAME_RE, answer, re.IGNORECASE)]
    if len(months) != len(set(months)):
        return False
    allowed_months = {
        match.group().lower()[:3]
        for match in re.finditer(MONTH_NAME_RE, str(facts.get("period_text") or ""), re.IGNORECASE)
    }
    if any(month not in allowed_months for month in months):
        return False
    if re.search(r"\bin\s+the\s+specified\s+period\b", text):
        return False
    if facts.get("found") and any(p in text for p in NO_RECORDS_PHRASES):
        return False
    if not _numbers(answer) <= _numbers(str(facts)):
        return False
    if INSTANCE_RE.search(text):
        return False
    if QUOTED_LABEL_RE.search(answer):
        return False
    if facts.get("groups") and BARE_NUMBER_RE.search(answer):
        return False
    if ON_RECORD_RE.search(answer):
        return False
    if RECORDS_WORD_RE.search(answer) and "record" not in str(facts.get("unit") or "").lower():
        return False
    if STATUS_ATTENDANCE_RE.search(answer):
        return False
    return True