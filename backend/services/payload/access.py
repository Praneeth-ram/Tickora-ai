# backend/services/payload/access.py
from backend.services.operation_registry import build_operation_registry
from backend.services.payload.entities import registry_for_role


def registry_for_session(session) -> dict[str, dict]:
    """The only registry the chat path may use. Built per request, filtered by role."""
    return registry_for_role(build_operation_registry(schema_name="public"), session.role)