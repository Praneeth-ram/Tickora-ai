"""Resolve an employee named in a question, only among employees the actor may access."""
import re
from sqlalchemy import text
from backend.security.access_policy import ADMIN, SUPER_ADMIN, Actor, scope_clause

CODE_RE = re.compile(r"\bEMP\d+\b", re.IGNORECASE)

# One message for every failure, so the chatbot never reveals whether a person exists.
NOT_FOUND_MESSAGE = (
    "I couldn't find that employee among the records you can access. "
    "Please check the name or employee code."
)

def _mentions(question: str, value: str) -> bool:
    return bool(re.search(rf"(?<!\w){re.escape(value)}(?!\w)", question, re.IGNORECASE))

def match_subject(rows, question: str) -> int | None:
    """Pure matching step: return the one employee id named in the question, or None."""
    hits = {
        row["id"]
        for row in rows
        if _mentions(question, row["employee_code"]) or _mentions(question, row["full_name"])
    }
    if not hits:
        first_name_hits = {
            row["id"]
            for row in rows
            if row["full_name"] and _mentions(question, row["full_name"].split()[0])
        }
        if len(first_name_hits) == 1:
            hits = first_name_hits
    return hits.pop() if len(hits) == 1 else None

def resolve_subject(connection, actor: Actor, question: str) -> int | None:
    """Return the employee id the question refers to, or None if none is uniquely in scope."""
    if actor.role not in {ADMIN, SUPER_ADMIN}:
        return None

    clause, params = scope_clause(actor, "attendance", "e.id")
    rows = connection.execute(
        text(f"""
            SELECT e.id, e.employee_code, e.full_name
            FROM public.employees e
            WHERE e.is_active = TRUE AND ({clause})
        """),
        params,
    ).mappings().all()

    return match_subject(rows, question)

NAME_RE = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b")
POSSESSIVE_NAME_RE = re.compile(r"\b([A-Za-z][A-Za-z'-]*)'s\b", re.IGNORECASE)
NOT_A_NAME = {
    "is", "are", "was", "were", "what", "when", "where", "which", "who", "how",
    "show", "list", "do", "does", "did", "can", "tell", "give", "the", "my", "your", "our",
    "it", "that", "there", "here", "today", "week", "month", "year",
    "employee", "manager", "task", "project", "team", "company", "organization",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
}

def _normalize_apostrophes(text: str) -> str:
    """Phones type curly apostrophes; the database stores straight ones."""
    return text.replace("\u2019", "'")

def load_non_person_phrases(connection, organization_id: int) -> frozenset[str]:
    """Known category names (leave types, holidays, loan components) that are not people."""
    rows = connection.execute(
        text("""
            SELECT name FROM public.leave_types WHERE organization_id = :org
            UNION
            SELECT name FROM public.holidays
            UNION
            SELECT component FROM public.loan_requests WHERE organization_id = :org
        """),
        {"org": organization_id},
    ).scalars().all()
    return frozenset(_normalize_apostrophes(name).strip() for name in rows if name)

def _strip_known_terms(question: str, known: frozenset[str]) -> str:
    """Remove known category names (case-insensitive) before looking for people."""
    remainder = _normalize_apostrophes(question)
    for term in sorted(known, key=len, reverse=True):  # longest first
        remainder = re.sub(
            rf"(?<!\w){re.escape(term)}(?!\w)", " ", remainder, flags=re.IGNORECASE
        )
    return remainder

def names_a_person(question: str, actor, non_person_phrases: frozenset[str] = frozenset()) -> bool:
    if CODE_RE.search(question):
        own = f"EMP{actor.employee_id:03d}"
        return any(code.upper() != own for code in CODE_RE.findall(question))
    remainder = _strip_known_terms(question, non_person_phrases)
    for match in NAME_RE.finditer(remainder):
        words = [word.lower() for word in match.group(0).split()]
        if not all(word in NOT_A_NAME for word in words):
            return True
    for match in POSSESSIVE_NAME_RE.finditer(remainder):
        if match.group(1).lower() not in NOT_A_NAME:
            return True
    return False