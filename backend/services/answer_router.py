TABLE_ROW_THRESHOLD = 5
BREAKDOWN_GROUP_LIMIT = 4


def choose_route(result: dict) -> str:
    rows = result.get("data") or []
    if result.get("show_table") and len(rows) > TABLE_ROW_THRESHOLD:
        return "table"
    if result.get("operation") == "group_by" and len(rows) > BREAKDOWN_GROUP_LIMIT:
        return "table"
    return "llm"