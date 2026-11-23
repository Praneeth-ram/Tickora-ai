import re


TABLE_REQUEST_RE = re.compile(r"\b(?:table|tabular|spreadsheet)\b", re.IGNORECASE)
LIST_REQUEST_RE = re.compile(
    r"^\s*(?:(?:please|can you|could you|would you|i want to|i need you to)\s+)*"
    r"(?:show|list|display)\b",
    re.IGNORECASE,
)


def choose_route(question: str) -> str:
    """Skip narration only when the user explicitly asks for a table or list."""
    if TABLE_REQUEST_RE.search(question) or LIST_REQUEST_RE.search(question):
        return "table"
    return "llm"
