import json
import re
from pathlib import Path

path = Path("data/intent_dataset_merged.jsonl")

patterns = {
    "Half-day and attendance metrics": r"\bhalf[- ]day|\babsent\b|\babsence\b|\blate days?\b|\bpresent days?\b",
    "Leave days versus leave requests": r"\bleave\b|\bvacation\b|\btime off\b",
    "Working days versus attendance": r"\bworking days?\b|\bwork days?\b|\bschedule\b|\bshift\b",
    "WFH days versus WFH requests": r"\bwfh\b|work[- ]from[- ]home",
    "Timesheet approval and submission": r"\btimesheet\b|\bsubmitted\b|\bapproved\b",
    "Holiday versus attendance": r"\bholiday\b|\bholidays\b|\bchristmas\b|\bgandhi jayanti\b",
}

rows = []
with path.open("r", encoding="utf-8-sig") as f:
    for line_number, line in enumerate(f, 1):
        if not line.strip():
            continue
        row = json.loads(line)
        rows.append((line_number, row))

for title, pattern in patterns.items():
    print("\n" + "=" * 72)
    print(title.upper())
    print("=" * 72)

    matches = [
        (line_no, row)
        for line_no, row in rows
        if re.search(pattern, row.get("text", ""), re.I)
    ]

    print(f"Matching examples: {len(matches)}")
    for line_no, row in matches:
        print(
            f"Line {line_no} | {row['text']} "
            f"| target={json.dumps(row.get('target', {}), ensure_ascii=False)}"
        )
