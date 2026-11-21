from backend.services.request_answer_builder import period_phrase

MINUTE_FIELDS = {"worked_minutes", "overtime_minutes"}
STATUS_LABELS = {
    "PRESENT": "present",
    "LATE": "late",
    "ABSENT": "absent",
    "HALF_DAY": "half day",
    "ON_LEAVE": "on leave",
}


def period_text(period: dict) -> str:
    from datetime import date
    start = period.get("start_date")
    end = period.get("end_date")
    if not start or not end:
        return "for the requested period"
    return period_phrase(date.fromisoformat(start), date.fromisoformat(end)).strip()


def compute_facts(question: str, plan: dict, period: dict, result: dict) -> dict:
    op = plan.get("operation_id", "")
    data = result.get("data")
    facts = {"question": question, "period_text": period_text(period)}
    field = plan.get("aggregate_field")

    if field in MINUTE_FIELDS and isinstance(data, list):
        total = sum(int(r.get(field) or 0) for r in data)
        # Expose hours and minutes only; the raw minute total must not reach the writer.
        facts.update({
            "measure": "overtime" if field == "overtime_minutes" else "worked time",
            "hours": total // 60,
            "minutes": total % 60,
            "found": bool(data),
        })
    elif op.endswith(".count") and isinstance(data, dict):
        facts.update({"count": int(data.get("count", 0)), "found": True})
        status = (plan.get("filters") or {}).get("status")
        if status:
            facts["status"] = str(status).replace("_", " ")
    elif op.endswith(".group_by") and isinstance(data, list):
        facts["groups"] = [
            {"label": STATUS_LABELS.get(str(r.get("group_value")), str(r.get("group_value")).lower()),
             "count": int(r.get("record_count", 0))}
            for r in data
        ]
        facts["found"] = bool(data)
    elif isinstance(data, list):
        facts.update({
            "total": len(data),
            "rows": data[:5],
            "truncated": len(data) > 5,
            "found": bool(data),
        })
    else:
        facts["found"] = False
    return facts