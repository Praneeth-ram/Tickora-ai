# import json
# import shutil
# from pathlib import Path

# path = Path("data/intent_dataset_expansion.jsonl")
# backup = Path("data/intent_dataset_expansion.before_status_fixes.jsonl")

# fixes = {
#     "List the timesheets I have not submitted yet": {
#         "new_text": "List the timesheets I have not submitted yet",
#         "intent": "timesheet_lookup",
#         "status": "DRAFT",
#     },
#     "Tell me whether my latest leave request was approved": {
#         "new_text": "Check the status of my latest leave request",
#         "intent": "leave_status",
#         "status": None,
#     },
# }

# if not path.exists():
#     raise SystemExit(f"File not found: {path}")

# if not backup.exists():
#     shutil.copy2(path, backup)
#     print(f"Backup created: {backup}")

# rows = []
# found = set()

# with path.open("r", encoding="utf-8-sig") as file:
#     for line in file:
#         if not line.strip():
#             continue

#         row = json.loads(line)
#         question = row.get("text", "")

#         if question in fixes:
#             fix = fixes[question]
#             target = row.get("target", {})

#             if target.get("intent") != fix["intent"]:
#                 raise SystemExit(
#                     f"Unexpected intent for {question!r}: {target}"
#                 )

#             row["text"] = fix["new_text"]

#             if fix["status"] is None:
#                 target.pop("status", None)
#             else:
#                 target["status"] = fix["status"]

#             row["target"] = target
#             found.add(question)
#             print(f"Fixed: {question}")
#             print(f"New target: {json.dumps(target, ensure_ascii=False)}")

#         rows.append(row)

# if found != set(fixes):
#     missing = set(fixes) - found
#     raise SystemExit(
#         f"Expected both records. Missing: {sorted(missing)}. "
#         "No changes written."
#     )

# with path.open("w", encoding="utf-8") as file:
#     for row in rows:
#         file.write(json.dumps(row, ensure_ascii=False) + "\n")

# print(f"\nSuccessfully fixed {len(found)} records.")
