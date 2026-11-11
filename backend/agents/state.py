from typing import Any, TypedDict

class ChatState(TypedDict, total=False):
    question: str
    session_id: str
    employee_id: int
    employee_code: str
    organization_id: int
    request_type: str
    normalized_question: str
    period: dict[str, Any]
    raw_plan: dict[str, Any]
    plan: dict[str, Any]
    status: str
    clarification: str | None
    result: dict[str, Any]