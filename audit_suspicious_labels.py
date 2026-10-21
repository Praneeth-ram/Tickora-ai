import json
import re
from pathlib import Path

files = [
    "data/intent_dataset.jsonl",
    "data/intent_dataset_extra.jsonl",
    "data/intent_dataset_expansion.jsonl",
    "data/intent_dataset_contrastive.jsonl",
    "data/intent_dataset_contrastive_v2.jsonl",
    "data/intent_dataset_contrastive_v3.jsonl",
]

checks = [
    (
        "Approval questions with suspicious status",
        re.compile(r"\b(approved|approval|rejected|pending)\b", re.I),
        lambda text, target: (
            target.get("status") == "LATE"
            or target.get("status") == "ABSENT"
            or target.get("status") == "PRESENT"
        ),
    ),
    (
        "Unsubmitted timesheets with SUBMITTED status",
        re.compile(r"\b(unsubmitted|not submitted|haven't submitted|have not submitted)\b", re.I),
        lambda text, target: (
            target.get("intent") == "timesheet_lookup"
            and target.get("status") == "SUBMITTED"
        ),
    ),
    (
        "Date ranges whose end precedes their start",
        re.compile(r"\b(between|from)\b", re.I),
        lambda text, target: (
            bool(target.get("start_date"))
            and bool(target.get("end_date"))
            and target["end_date"] < target["start_date"]
        ),
    ),
]

for filename in files:
    path = Path(filename)
    if not path.exists():
        print(f"\nMISSING FILE: {filename}")
        continue

    with path.open("r", encoding="utf-8-sig") as file:
        for line_no, line in enumerate(file, 1):
            if not line.strip():
                continue

            row = json.loads(line)
            text = row.get("text", "")
            target = row.get("target", {})

            for title, pattern, suspicious in checks:
                if pattern.search(text) and suspicious(text, target):
                    print(f"\n[{title}]")
                    print(f"File: {filename} | Line: {line_no}")
                    print(f"Question: {text}")
                    print(f"Target: {json.dumps(target, ensure_ascii=False)}")
