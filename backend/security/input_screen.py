import re

# Phrases that try to override instructions, change roles, or reach data outside
# the approved query path. Matching is case-insensitive and tolerant of spacing.
_INJECTION_PATTERNS = [
    r"ignore\s+(?:all\s+|your\s+|the\s+|previous\s+|above\s+)*(?:rules|instructions|prompt|guidelines)",
    r"disregard\s+(?:all\s+|your\s+|the\s+|previous\s+)*(?:rules|instructions|prompt)",
    r"reveal\s+(?:your\s+|the\s+)?(?:system\s+)?(?:prompt|instructions)",
    r"you\s+are\s+now\b",
    r"act\s+as\s+(?:an?\s+)?(?:admin|administrator|root|developer|dba)",
    r"\bsystem\s*:",
    r"<\s*/?\s*(?:system|assistant|user)\s*>",
    r"\bdrop\s+table\b",
    r"\bdelete\s+from\b",
    r"\binsert\s+into\b",
    r"\bunion\s+select\b",
    r";\s*--",
    r"\bselect\s+\*\s+from\b",
    r"\bpg_\w+\b",
    r"\binformation_schema\b",
    r"\bdump\s+(?:the\s+)?(?:database|table|schema)\b",
]

_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)

MAX_QUESTION_LENGTH = 500

INJECTION_MESSAGE = (
    "I can't process that request. Please ask a question about your own records, "
    "such as attendance, leave, or payroll."
)

LENGTH_MESSAGE = (
    f"That question is too long. Please keep it under {MAX_QUESTION_LENGTH} characters."
)


def screen_question(question: str) -> str | None:
    """Return a refusal message if the question should be blocked, otherwise None."""
    if len(question) > MAX_QUESTION_LENGTH:
        return LENGTH_MESSAGE
    if _INJECTION_RE.search(question):
        return INJECTION_MESSAGE
    return None