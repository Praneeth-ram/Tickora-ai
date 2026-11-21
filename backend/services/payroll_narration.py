from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
import re
from typing import Any

from backend.services.request_answer_builder import as_date, period_phrase

PAYROLL_METRICS = {
    "gross_amount": (
        "gross amount",
        re.compile(r"\bgross(?:\s+(?:amount|pay|salary|earnings))?\b", re.IGNORECASE),
    ),
    "deduction_amount": (
        "deduction amount",
        re.compile(r"\b(?:deductions?|deducted)\b", re.IGNORECASE),
    ),
    "net_amount": (
        "net amount",
        re.compile(r"\bnet(?:\s+(?:amount|pay|salary|income))?\b", re.IGNORECASE),
    ),
}

_TOTAL_RE = re.compile(
    r"\b(?:total|cumulative|combined|sum\s+of|overall\s+total)\b",
    re.IGNORECASE,
)
_TABLE_QUERY_RE = re.compile(
    r"\b(?:table|breakdown|payroll\s+(?:details|records?|history)|"
    r"(?:list|show|display)\s+(?:all\s+)?(?:my\s+)?(?:payroll|payslips?|pay\s*slips?)|"
    r"(?:all|every|each)\s+(?:my\s+)?(?:payroll|payslips?))\b",
    re.IGNORECASE,
)
_NUMBER_RE = re.compile(
    r"(?<![\w])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?![\w])"
)
_CURRENCY_AMOUNT_RE = re.compile(
    r"(?<![A-Z])(?P<currency>[A-Z]{3})\s*"
    r"(?P<amount>[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)"
    r"|(?P<amount_after>[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*"
    r"(?P<currency_after>[A-Z]{3})(?![A-Z])",
    re.IGNORECASE,
)
_CURRENCY_RE = re.compile(r"\b[A-Z]{3}\b")


def requested_payroll_metrics(question: str) -> list[str]:
    """Return only explicit payroll amounts requested by the user."""
    return [
        field
        for field, definition in PAYROLL_METRICS.items()
        if definition[1].search(question)
    ]


def is_payroll_detail_question(question: str) -> bool:
    return bool(
        requested_payroll_metrics(question)
        and not _TABLE_QUERY_RE.search(question)
        and not re.search(
            r"\b(?:all|every|each)\s+(?:the\s+)?employees?\b"
            r"|\b(?:everyone|everybody)\b",
            question,
            re.IGNORECASE,
        )
    )


def _decimal_amount(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return amount if amount.is_finite() else None


def _covers_requested_months(
    rows: list[dict[str, Any]], start: date, end: date
) -> bool:
    requested: set[tuple[int, int]] = set()
    cursor = start.replace(day=1)
    last_month = end.replace(day=1)
    while cursor <= last_month:
        requested.add((cursor.year, cursor.month))
        cursor = (
            date(cursor.year + 1, 1, 1)
            if cursor.month == 12
            else date(cursor.year, cursor.month + 1, 1)
        )

    covered: set[tuple[int, int]] = set()
    for row in rows:
        row_start = as_date(row.get("period_start"))
        row_end = as_date(row.get("period_end"))
        if row_start is None or row_end is None:
            return False
        cursor = row_start.replace(day=1)
        last_month = row_end.replace(day=1)
        while cursor <= last_month:
            covered.add((cursor.year, cursor.month))
            cursor = (
                date(cursor.year + 1, 1, 1)
                if cursor.month == 12
                else date(cursor.year, cursor.month + 1, 1)
            )
    return requested.issubset(covered)


def build_payroll_facts(
    question: str, period: dict[str, Any], rows: Any
) -> dict[str, Any] | None:
    """Build minimal, currency-bound facts for explicit personal amount questions."""
    metrics = requested_payroll_metrics(question)
    if not is_payroll_detail_question(question) or not isinstance(rows, list) or not rows:
        return None
    if not all(isinstance(row, dict) for row in rows):
        return None

    start = as_date(period.get("start_date"))
    end = as_date(period.get("end_date"))
    asks_total = bool(_TOTAL_RE.search(question))
    if asks_total:
        if start is None or end is None or not _covers_requested_months(rows, start, end):
            return None
    elif len(rows) != 1:
        return None

    period_text = period_phrase(start, end).strip() if start and end else "on record"
    metric_facts = []
    for field in metrics:
        amounts_by_currency: dict[str, Decimal] = defaultdict(Decimal)
        row_amounts = []
        for row in rows:
            amount = _decimal_amount(row.get(field))
            currency = row.get("currency")
            if (
                amount is None
                or not isinstance(currency, str)
                or not re.fullmatch(r"[A-Za-z]{3}", currency.strip())
            ):
                return None
            currency = currency.strip().upper()
            if asks_total:
                amounts_by_currency[currency] += amount
            else:
                row_amounts.append({
                    "value": format(amount, "f"),
                    "currency": currency,
                })

        values = (
            [
                {"value": format(amount, "f"), "currency": currency}
                for currency, amount in sorted(amounts_by_currency.items())
            ]
            if asks_total
            else row_amounts
        )
        metric_facts.append({
            "field": field,
            "label": PAYROLL_METRICS[field][0],
            "amounts": values,
        })

    return {
        "entity": "payroll",
        "shape": "total" if asks_total else "amount",
        "period_text": period_text,
        "metrics": metric_facts,
        "found": True,
    }


def passes_payroll_answer_check(answer: str, facts: dict[str, Any]) -> bool:
    """Require every requested amount and currency, and reject any extra numbers."""
    if not answer or len(answer.split()) < 5:
        return False

    metrics = facts.get("metrics")
    if not isinstance(metrics, list) or not metrics:
        return False
    expected_fields = {metric.get("field") for metric in metrics}
    mentioned_fields = {
        field
        for field, definition in PAYROLL_METRICS.items()
        if definition[1].search(answer)
    }
    if mentioned_fields != expected_fields:
        return False

    period_text = str(facts.get("period_text") or "").strip()
    checked_text = answer
    if period_text and period_text != "on record":
        if period_text.lower() not in answer.lower():
            return False
        checked_text = re.sub(
            re.escape(period_text), "", answer, flags=re.IGNORECASE
        )

    expected_amounts: Counter[Decimal] = Counter()
    expected_pairs: Counter[tuple[str, Decimal]] = Counter()
    for metric in metrics:
        for value in metric.get("amounts") or []:
            amount = _decimal_amount(value.get("value"))
            currency = value.get("currency")
            if (
                amount is None
                or not isinstance(currency, str)
                or not re.fullmatch(r"[A-Z]{3}", currency)
            ):
                return False
            expected_amounts[amount] += 1
            expected_pairs[(currency, amount)] += 1

    answer_amounts: Counter[Decimal] = Counter()
    try:
        for token in _NUMBER_RE.findall(checked_text):
            answer_amounts[Decimal(token.replace(",", ""))] += 1
    except InvalidOperation:
        return False
    if answer_amounts != expected_amounts:
        return False

    answer_pairs: Counter[tuple[str, Decimal]] = Counter()
    try:
        for match in _CURRENCY_AMOUNT_RE.finditer(checked_text):
            currency = match.group("currency") or match.group("currency_after")
            amount = match.group("amount") or match.group("amount_after")
            answer_pairs[(currency.upper(), Decimal(amount.replace(",", "")))] += 1
    except (AttributeError, InvalidOperation):
        return False
    if answer_pairs != expected_pairs:
        return False

    expected_currencies = Counter(
        pair[0] for pair in expected_pairs.elements()
    )
    return Counter(code for code in _CURRENCY_RE.findall(checked_text)) == expected_currencies
