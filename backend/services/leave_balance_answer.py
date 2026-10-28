"""Leave balance questions: which metric, which leave type, which year, and the sentence.

Nothing here hardcodes leave-type names or IDs. Types come from the database
(the leave_types registry entry), and matching uses their names and codes.
"""

import re
from typing import Any

METRIC_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("pending", re.compile(r"\bpending\b")),
    ("used", re.compile(r"\b(?:used|use|uses|taken|take|took|consumed|utili[sz]ed|spent)\b")),
    ("allocated", re.compile(r"\b(?:allocated|entitled|entitlement|granted|quota)\b")),
    ("remaining", re.compile(r"\b(?:balance|left|remaining|available)\b")),
]
YEAR_RE = re.compile(r"\b(20\d{2})\b")
REQUEST_WORDS_RE = re.compile(
    r"\b(?:requests?|applied|apply|approved|rejected|submitted|cancel+ed|canceled)\b"
)
LEAVE_WORD_RE = re.compile(r"\bleaves?\b")
METRIC_PHRASE = {
    "allocated": "allocated",
    "used": "used",
    "pending": "pending",
    "remaining": "remaining",
}

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
    """A balance question names a balance metric and a leave word, without request words.

    'pending leave requests' is a request question and is excluded.
    """
    q = question.lower()
    if REQUEST_WORDS_RE.search(q):
        return False
    if detect_metric(q) is None:
        return False
    return bool(LEAVE_WORD_RE.search(q)) or bool(re.search(r"\b(?:casual|sick|earned|unpaid|maternity)\b", q))

def format_days(value: Any) -> str:
    number = float(value or 0)
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}".rstrip("0").rstrip(".")

def _label(leave_type: dict[str, Any]) -> str:
    name = str(leave_type.get("name") or leave_type.get("code") or "leave").strip()
    return name if name.lower().endswith("leave") else f"{name} leave"

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
            return f"You have {allocated} allocated {label} days in {year}."
        if metric == "used":
            return f"You have used {used} {label} days in {year}."
        if metric == "pending":
            return f"You have {pending} pending {label} days in {year}."
        if metric == "remaining":
            return (
                f"You have {remaining} {label} days left in {year} "
                f"({allocated} allocated, {used} used, {pending} pending)."
            )
        return (
            f"Your {label} balance for {year}: {allocated} allocated, "
            f"{used} used, {pending} pending, {remaining} left."
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
        return f"You have {format_days(total)} {METRIC_PHRASE[metric]} leave days in {year}{detail}."

    lines = [f"Your leave balance for {year}:"]
    for r in rows:
        label = _label(by_id.get(r.get("leave_type_id"), {"name": f"Leave type {r.get('leave_type_id')}"}))
        lines.append(
            f"- {label}: {format_days(_remaining(r))} left "
            f"({format_days(r.get('allocated_days'))} allocated, "
            f"{format_days(r.get('used_days'))} used, "
            f"{format_days(r.get('pending_days'))} pending)."
        )
    total_left = sum(_remaining(r) for r in rows)
    lines.append(f"Total left: {format_days(total_left)} days.")
    return "\n".join(lines)