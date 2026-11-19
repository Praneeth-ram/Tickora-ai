from datetime import date


SHORT_LIST_MAX_DAYS = 31
_OPERATION_SHAPES = {"list", "count", "sum", "group_by"}


def choose_shape(
    operation_id: str,
    start_date: date | None,
    end_date: date | None,
) -> str:
    """Choose the response shape for a registered operation."""
    _, separator, operation = operation_id.rpartition(".")
    if not separator or operation not in _OPERATION_SHAPES:
        raise ValueError(f"Unsupported operation id: {operation_id!r}")

    if operation != "list":
        return operation

    if start_date is not None and end_date is not None:
        days = (end_date - start_date).days + 1
        if days == 1:
            return "single"
        if days > SHORT_LIST_MAX_DAYS:
            return "summary"

    return "list_short"
