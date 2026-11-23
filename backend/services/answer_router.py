import re

TABLE_REQUEST_RE = re.compile(r"\b(?:table|tabular|spreadsheet)\b", re.IGNORECASE)
LIST_REQUEST_RE = re.compile(
    r"^\s*(?:(?:please|can you|could you|would you|i want to|i need you to)\s+)*"
    r"(?:show|list|display)\b",
    re.IGNORECASE,
)
TABLE_ROW_THRESHOLD = 5


def choose_route(question: str, row_count: int = 0) -> str:
    """Table only for explicit table requests, or list requests with many rows."""
    if TABLE_REQUEST_RE.search(question):
        return "table"
    if LIST_REQUEST_RE.search(question) and row_count > TABLE_ROW_THRESHOLD:
        return "table"
    return "llm"