"""Leave balance questions: which metric, which leave type, which year, and the sentence.

Nothing here hardcodes leave-type names or IDs. Types come from the database
(the leave_types registry entry), and matching uses their names and codes.
"""

import re
from typing import Any

METRIC_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("pending", re.compile(r"\bpending\b")),
    ("used", re.compile(r"\b(?:used|use|uses|taken|take|took|consumed|utili[sz]ed|spent)\b")),
    ("allocated", re.compile(r"\b(?:allocated|entitled|entitlement|granted|quota|accrued|credited)\b")),
    ("remaining", re.compile(r"\b(?:balance|left|remaining|available|carri(?:ed)?\s*over|carry\s*over)\b")),
]
YEAR_RE = re.compile(r"\b(20\d{2})\b")
LEAVE_WORD_RE = re.compile(r"\bleaves?\b")
METRIC_PHRASE = {
    "allocated": "allocated",
    "used": "used",
    "pending": "pending",
    "remaining": "remaining",
}

# Words that name a specific leave category; their presence alone signals a balance
# question even when no explicit metric word (allocated/remaining/used) appears.
_LEAVE_TYPE_WORDS_RE = re.compile(
    r"\b(?:casual|sick|earned|unpaid|maternity|paternity|comp(?:\s*off)?|privilege|annual|study|bereavement)\b"
)

# Broad metric detector — includes natural-language phrases and synonyms not covered
# by the compact METRIC_PATTERNS list used for answer generation.
_EXTENDED_METRIC_RE = re.compile(
    r"\b(?:"
    r"allocated|entitled|entitlement|granted|quota|accrued|credited|"
    r"used|use|uses|taken|take|took|consumed|utili[sz]ed|spent|"
    r"pending|"
    r"balance|left|remaining|available|carri(?:ed)?\s*over|carry\s*over|"
    r"how\s+many\s+(?:\w+\s+)*(?:leave\s+)?days?|"
    r"how\s+much\s+leave|"
    r"leave\s+days?|days?\s+(?:of\s+)?leave|"
    r"leave\s+credit|credit"
    r")\b",
    re.IGNORECASE,
)

# Request-action words that definitively indicate a leave *request* workflow, not a
# balance query.  Status-describing words such as "approved", "rejected", and
# "submitted" are intentionally excluded — a user can legitimately ask
# "how many approved leave days do I have left?", which is a balance question.
REQUEST_WORDS_RE = re.compile(
    r"\b(?:requests?|applied|apply|cancell?(?:ed|ing)?|cancel)\b",
    re.IGNORECASE,
)


def detect_metric(question: str) -> str | None:
    """The first balance metric the question names, in priority order."""
    q = question.lower()
    for name, pattern in METRIC_PATTERNS:
        if pattern.search(q):
            return name
    return None


def detect_year(question: str, default_year: int) -> int:
    matches = YEAR_RE.findall(question)
    return int(matches[-1]) if matches else default_year


def match_leave_type(question: str, leave_types: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the leave type whose name or code appears in the question, longest match first."""
    q = question.lower()
    best: dict[str, Any] | None = None
    best_length = 0
    for leave_type in leave_types:
        candidates = set()
        for raw in (leave_type.get("name"), leave_type.get("code")):
            if not raw:
                continue
            text = str(raw).lower().replace("_", " ").strip()
            candidates.add(text)
            core = re.sub(r"\s+leave$", "", text).strip()
            if core:
                candidates.add(core)
        for candidate in candidates:
            if len(candidate) > best_length and re.search(rf"\b{re.escape(candidate)}\b", q):
                best, best_length = leave_type, len(candidate)
    return best


def is_leave_balance_question(question: str) -> bool:
    """Return True when the question is clearly about leave balance / quota.

    Rules (checked in priority order):
    1. Exclude questions with unmistakable leave-request action words (apply,
       request, cancel).  "approved" / "submitted" are intentionally kept so
       questions like "how many approved leave days do I have?" are accepted.
    2. Accept when any balance metric (including extended synonyms) is present
       together with any leave-topic indicator.
    3. Accept when a named leave type (sick, casual, …) appears together with
       a days/leave word even without an explicit metric, e.g.
       "how many sick days do I have?".
    """
    q = question.lower()
    if REQUEST_WORDS_RE.search(q):
        return False
    has_leave_word = bool(LEAVE_WORD_RE.search(q))
    has_leave_type = bool(_LEAVE_TYPE_WORDS_RE.search(q))
    has_metric = bool(_EXTENDED_METRIC_RE.search(q))
    # Rule 2: metric word + leave indicator
    if has_metric and (has_leave_word or has_leave_type):
        return True
    # Rule 3: named leave type + days/leave word without metric
    # e.g. "how many sick days do I have?"
    if has_leave_type:
        return bool(re.search(r"\bdays?\b|\bleaves?\b", q))
    return False


def format_days(value: Any) -> str:
    number = float(value or 0)
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}".rstrip("0").rstrip(".")


def _label(leave_type: dict[str, Any]) -> str:
    name = str(leave_type.get("name") or leave_type.get("code") or "leave").strip()
    return name if name.lower().endswith("leave") else f"{name} leave"


def _day_noun(value: Any) -> str:
    return "day" if float(value or 0) == 1 else "days"


def _remaining(row: dict[str, Any]) -> float:
    return float(row.get("allocated_days") or 0) - float(row.get("used_days") or 0) - float(row.get("pending_days") or 0)


def enrich_rows(rows: list[dict[str, Any]], leave_types: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add a leave_type name to each balance row so tables show names, not IDs."""
    names = {lt.get("id"): _label(lt) for lt in leave_types}
    enriched = []
    for row in rows:
        item = dict(row)
        item["leave_type"] = names.get(row.get("leave_type_id"), f"Leave type {row.get('leave_type_id')}")
        item["year"] = str(row.get("year", ""))
        enriched.append(item)
    return enriched


def answer_leave_balance(
    rows: list[dict[str, Any]],
    leave_types: list[dict[str, Any]],
    year: int,
    metric: str | None,
    selected: dict[str, Any] | None,
) -> str:
    rows = [r for r in rows if str(r.get("year")) == str(year)]
    if selected is not None:
        rows = [r for r in rows if r.get("leave_type_id") == selected.get("id")]

    if not rows:
        if selected is not None:
            return f"I couldn't find a {_label(selected)} balance for {year}."
        return f"I couldn't find any leave balance for {year}."

    by_id = {lt.get("id"): lt for lt in leave_types}

    if selected is not None:
        row = rows[0]
        label = _label(selected)
        allocated = format_days(row.get("allocated_days"))
        used = format_days(row.get("used_days"))
        pending = format_days(row.get("pending_days"))
        remaining = format_days(_remaining(row))
        if metric == "allocated":
            return f"You have {allocated} allocated {label} {_day_noun(row.get('allocated_days'))} in {year}."
        if metric == "used":
            return f"You have used {used} {label} {_day_noun(row.get('used_days'))} in {year}."
        if metric == "pending":
            return f"You have {pending} pending {label} {_day_noun(row.get('pending_days'))} in {year}."
        if metric == "remaining":
            return (
                f"You have {remaining} {label} {_day_noun(_remaining(row))} remaining in {year} "
                f"({allocated} allocated, {used} used, {pending} pending)."
            )
        return (
            f"Your {label} balance for {year} is {remaining} {_day_noun(_remaining(row))}: "
            f"{allocated} allocated, {used} used, and {pending} pending."
        )

    if metric in METRIC_PHRASE and metric != "remaining":
        field = {"allocated": "allocated_days", "used": "used_days", "pending": "pending_days"}[metric]
        total = sum(float(r.get(field) or 0) for r in rows)
        parts = [
            f"{format_days(r.get(field))} {_label(by_id.get(r.get('leave_type_id'), {}))}"
            for r in rows
            if float(r.get(field) or 0) > 0
        ]
        detail = f" ({', '.join(parts)})" if parts else ""
        return (
            f"You have {format_days(total)} {METRIC_PHRASE[metric]} leave "
            f"{_day_noun(total)} in {year}{detail}."
        )

    lines = [f"Your leave balance for {year}:"]
    for r in rows:
        label = _label(by_id.get(r.get("leave_type_id"), {"name": f"Leave type {r.get('leave_type_id')}"}))
        lines.append(
            f"- {label}: {format_days(_remaining(r))} {_day_noun(_remaining(r))} remaining "
            f"({format_days(r.get('allocated_days'))} allocated, "
            f"{format_days(r.get('used_days'))} used, and "
            f"{format_days(r.get('pending_days'))} pending)."
        )
    total_left = sum(_remaining(r) for r in rows)
    lines.append(f"Total remaining: {format_days(total_left)} {_day_noun(total_left)}.")
    return "\n".join(lines)