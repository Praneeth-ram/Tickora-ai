# import json
# from pathlib import Path

# source_files = [
#     "data/intent_dataset.jsonl",
#     "data/intent_dataset_extra.jsonl",
#     "data/intent_dataset_expansion.jsonl",
#     "data/intent_dataset_contrastive.jsonl",
#     "data/intent_dataset_contrastive_v2.jsonl",
#     "data/intent_dataset_contrastive_v3.jsonl",
# ]

# needles = [
#     "Tell me whether my latest leave request was approved",
#     "Tell me whether my latest WFH request was approved",
#     "Display leave requests between 2026-10-01 and 2026-10-15",
#     "Display WFH requests between 2026-10-01 and 2026-10-15",
#     "Give me the timesheet records for 2026-10-01 to 2026-10-15",
#     "List the timesheets I have not submitted yet",
#     "Tell me my present and absent totals for this week",
#     "Summarize the number of half days this month",
# ]

# for filename in source_files:
#     path = Path(filename)
#     if not path.exists():
#         print(f"\nMISSING FILE: {filename}")
#         continue

#     with path.open("r", encoding="utf-8-sig") as file:
#         for line_no, line in enumerate(file, start=1):
#             if not line.strip():
#                 continue

#             row = json.loads(line)
#             text = row.get("text", "")

#             if any(needle.casefold() in text.casefold() for needle in needles):
#                 print(f"\nFile: {filename} | Line: {line_no}")
#                 print(f"Question: {text}")
#                 print(f"Target: {json.dumps(row.get('target', {}), ensure_ascii=False)}")
