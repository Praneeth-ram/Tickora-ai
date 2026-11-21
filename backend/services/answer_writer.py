import json
import re
from backend.services.model_inference import generate_text

ANSWER_RULES = """\
You answer an HR question using only the FACTS (JSON).

Rules:
1. Write one complete sentence, or two at most. Never reply with bare numbers.
2. Answer the question that was asked.
3. Use only the values in FACTS. Do not add, subtract, or convert any value.
4. Use period_text exactly as given for the period.
5. If found is false, say no matching records were found for that period.
6. Refer to the user as "you".
7. Do not mention databases, queries, JSON, or the system.
8. The user is the person being described. Always say "you" or "your". Never say "employees".
9. For attendance counts, always say "days", never "instances", "times", or "records".
10. Never put a space before a comma or full stop.
11. Never say "days" for hours or minutes. Use "hours" and "minutes" only for time totals.
12. Use singular and plural correctly: "1 hour", "2 hours", "1 day", "2 days".
13. Do not use "I" as the subject. Use "you".
"""

NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")

def write_answer(question: str, payload: dict) -> str:
    facts = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    return generate_text(ANSWER_RULES, f"Question: {question}\nFACTS: {facts}", max_new_tokens=150).strip()

def _numbers(text: str) -> set[str]:
    out = set()
    for raw in NUMBER_RE.findall(text):
        value = float(raw)
        out.add(str(int(value)) if value.is_integer() else str(value))
    return out

NO_RECORDS_PHRASES = ("no matching records", "no records", "not found", "no attendance")

def passes_answer_check(answer: str, facts: dict) -> bool:
    text = answer.lower()
    if not answer or len(answer.split()) < 6:
        return False
    if facts.get("found") and any(p in text for p in NO_RECORDS_PHRASES):
        return False
    if facts.get("measure") in {"worked time", "overtime"}:
        if "day" in text or "hour" not in text:
            return False
    if not _numbers(answer) <= _numbers(json.dumps(facts, default=str)):
        return False
    return True