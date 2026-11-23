import json
import re
from backend.services.model_inference import generate_text

BASE_RULES = """\
You answer an HR question using only the FACTS (JSON).

Rules:
1. Write one or two complete sentences. Never reply with bare numbers.
2. Answer only the question that was asked.
3. Use only values in FACTS. Do not add, subtract, convert, or round any value.
4. Use period_text exactly as given. Never put a comma between a month and a year.
5. Refer to the user as "you". Do not mention databases, queries, JSON, or the system.
6. Use the unit from FACTS exactly. Never write "records" or "on record".
7. Use "1 day" and "2 days", "1 hour" and "2 hours". Use the singular only for a count of 1.
8. If the count is 0, write "No" followed by the unit from FACTS, then "were found" and period_text. Do not use any month or year that is not in period_text.
9. Do not repeat the same figure in more than one sentence.
10. Never write "the specified period", "the requested period", or "the period".
11. Use only names and statuses that appear in FACTS. Never write "otherwise", "all", or "other statuses".
"""

ENTITY_RULES = {
    "attendance": (
        "Mention only statuses listed in FACTS. "
        "Use hours and minutes only for time totals, never days. "
        "For a single record, write one full sentence that starts with 'Your' "
        "and states the value of the field asked. Do not repeat the date more than once."
    ),
    "leave_request": 'Use the unit "leave requests".',
    "leave_balance": (
        "Answer the leave type or total the question asks for, using the "
        "remaining, allocated, used, and pending figures exactly as in FACTS."
    ),
    "leave_type": "When asked which leave types exist, name them from FACTS.",
    "wfh_request": 'Use the unit "work-from-home requests".',
    "timesheet": "State the count or status from FACTS. Do not list dates unless asked.",
    "task": "Use the task status labels exactly as in FACTS.",
    "holiday": 'Use the unit "holidays".',
    "attendance_punch": 'Use the unit "clock punches". Give times exactly as in FACTS.',
    "attendance_adjustment": 'Use the unit "attendance adjustments".',
    "payroll": (
        "Write each amount with its currency code exactly as in FACTS. "
        "Do not round, convert, or add another amount."
    ),
}


def build_rules(payload: dict) -> str:
    entity = str(payload.get("entity") or "").lower()
    extra = ENTITY_RULES.get(entity, "")
    fields = [str(f) for f in (payload.get("requested_fields") or []) if str(f).strip()]
    field_line = (
        f"\nAnswer only about: {', '.join(fields)}. Do not answer with other fields.\n"
        if fields else ""
    )
    return BASE_RULES + (f"\nEntity rule: {extra}\n" if extra else "") + field_line


def write_answer(question: str, payload: dict) -> str:
    facts = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    return generate_text(
        build_rules(payload),
        f"Question: {question}\nFACTS: {facts}",
        max_new_tokens=150,
    ).strip()

# Backward-compatible name for callers and tests that import the base prompt.
ANSWER_RULES = BASE_RULES

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
QUOTED_LABEL_RE = re.compile(r"['\"][A-Za-z][A-Za-z ]{1,30}['\"]")
BARE_NUMBER_RE = re.compile(
    r"(?<![\w.,])(?!(?:19|20)\d{2}\b)\d+(?:\.\d+)?\b(?!\s*[A-Za-z%])"
)
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

COUNT_VERB_RE = re.compile(
    r"\b(?:1|one)\s+\w+(?:\s+\w+)?\s+(?:were|are)\b|"
    r"\b(?:0|[2-9]\d*|\d{2,})(?!\d)(?!\s*(?:October|November|September|August|July|June|May|April|March|February|January|December)\b)\s+\w+(?:\s+\w+)?\s+(?:was|is)\b",
    re.IGNORECASE,
)

def normalize_answer(answer: str) -> str:
    """Remove the comma between month and year, and a repeated month.
    "October, 2026" -> "October 2026"
    "October, October, 2026" -> "October 2026"
    """
    return MONTH_YEAR_COMMA_RE.sub(r"\1 \2", answer)

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

FOREIGN_NOUNS = (
    "leave requests", "leave request", "work-from-home requests",
    "work from home requests", "timesheets", "timesheet", "holidays",
    "holiday", "tasks", "task", "clock punches", "attendance adjustments",
    "payslips", "payslip",
)

def _stem_phrase(value: str) -> str:
    return re.sub(r"(?:es|s)\b", "", value.lower().strip())


def _has_foreign_noun(answer: str, facts: dict) -> bool:
    text = answer.lower()
    allowed = _stem_phrase(
        " ".join(str(facts.get(k) or "") for k in ("unit", "unit_singular", "entity"))
    )
    for noun in FOREIGN_NOUNS:
        if re.search(rf"\b{re.escape(noun)}\b", text) and _stem_phrase(noun) not in allowed:
            return True
    return False

LEAVE_NAME_RE = re.compile(r"\b[A-Z][a-z]+ Leave\b")
NEG_STATUS_RE = re.compile(
    r"\bno\s+(?:\w+\s+){0,3}were\s+(?:present|late|absent)\b", re.IGNORECASE
)
NOT_STATUS_RE = re.compile(r"\bnot\s+(\w+)\b", re.IGNORECASE)

def _has_unknown_leave_name(answer: str, facts: dict) -> bool:
    known = str(facts).lower()
    return any(name.lower() not in known for name in LEAVE_NAME_RE.findall(answer))

def answer_check_failure(answer: str, facts: dict) -> str | None:
    """Return the name of the first failed check, or None when the answer passes."""
    text = answer.lower()
    if not answer or len(answer.split()) < 5:
        return "too_short"
    if _has_negated_status(text, facts):
        return "negated_status"
    if _has_unfounded_attendance_status(answer, facts):
        return "unfounded_status"
    if _has_invalid_unit_grammar(answer):
        return "unit_grammar"
    if _has_invalid_count_unit(answer, facts):
        return "count_unit"
    if PAREN_MINUTES_RE.search(answer):
        return "paren_minutes"
    if facts.get("measure") in {"worked time", "overtime"} and (
        DAY_WORD_RE.search(text) or "hour" not in text
    ):
        return "time_measure_unit"
    if MONTH_YEAR_COMMA_RE.search(answer):
        return "month_year_comma"
    if RELATIVE_MONTH_RE.search(answer):
        return "relative_month"
    if COUNT_VERB_RE.search(answer):
        return "count_verb_agreement"
    if _has_foreign_noun(answer, facts):
        return "foreign_noun"
    months = [m.group().lower()[:3] for m in re.finditer(MONTH_NAME_RE, answer, re.IGNORECASE)]
    if len(months) > 2 and len(set(months)) == 1:
        return "repeated_month"
    allowed_months = {
        m.group().lower()[:3]
        for m in re.finditer(MONTH_NAME_RE, str(facts.get("period_text") or ""), re.IGNORECASE)
    }
    if any(month not in allowed_months for month in months):
        return "month_not_in_period"
    if re.search(r"\bin\s+the\s+specified\s+period\b", text):
        return "specified_period"
    if facts.get("found") and any(p in text for p in NO_RECORDS_PHRASES):
        return "no_records_phrase"
    if not _numbers(answer) <= _numbers(str(facts)):
        return "number_not_in_facts"
    if INSTANCE_RE.search(text):
        return "instance_word"
    if QUOTED_LABEL_RE.search(answer):
        return "quoted_label"
    if facts.get("groups") and BARE_NUMBER_RE.search(answer):
        return "bare_number"
    if str(facts.get("period_text") or "").lower() != "on record" and ON_RECORD_RE.search(answer):
        return "on_record"
    if RECORDS_WORD_RE.search(ON_RECORD_RE.sub("", answer)) and "record" not in str(facts.get("unit") or "").lower():
        return "records_word"
    if STATUS_ATTENDANCE_RE.search(answer):
        return "status_attendance"
    if _has_unknown_leave_name(answer, facts):
        return "unknown_leave_name"
    if NEG_STATUS_RE.search(answer):
        return "negated_status_phrase"
    if re.search(r"\bI\b", answer):
        return "first_person_I"
    for m in NOT_STATUS_RE.finditer(answer):
        word = m.group(1).lower()
        if word in str(facts).lower():
            return "negated_fact_status"
    return None



def passes_answer_check(answer: str, facts: dict) -> bool:
    return answer_check_failure(answer, facts) is None