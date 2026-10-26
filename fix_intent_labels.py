# import json
# import shutil
# from pathlib import Path

# path = Path("data/intent_dataset_expansion.jsonl")
# backup = Path("data/intent_dataset_expansion.before_label_fixes.jsonl")

# if not path.exists():
#     raise SystemExit(f"File not found: {path}")

# if not backup.exists():
#     shutil.copy2(path, backup)
#     print(f"Backup created: {backup}")
# else:
#     print(f"Backup already exists: {backup}")

# targets = {
#     "Display leave requests between 2026-10-01 and 2026-10-15": "leave_status",
#     "Display WFH requests between 2026-10-01 and 2026-10-15": "wfh_status",
# }

# updated = 0
# output = []

# with path.open("r", encoding="utf-8-sig") as file:
#     for line in file:
#         if not line.strip():
#             output.append(line)
#             continue

#         row = json.loads(line)
#         question = row.get("text", "")
#         target = row.get("target", {})

#         if question in targets:
#             expected_intent = targets[question]

#             if target.get("intent") != expected_intent:
#                 raise ValueError(
#                     f"Unexpected intent for {question!r}: {target}"
#                 )

#             if (
#                 target.get("start_date") == "2026-10-01"
#                 and target.get("end_date") == "2026-10-01"
#             ):
#                 target["end_date"] = "2026-10-15"
#                 row["target"] = target
#                 updated += 1
#                 print(f"Fixed: {question}")

#         output.append(json.dumps(row, ensure_ascii=False) + "\n")

# if updated != 2:
#     raise SystemExit(
#         f"Expected to fix 2 records, but fixed {updated}. "
#         "Review the file before proceeding."
#     )

# with path.open("w", encoding="utf-8") as file:
#     file.writelines(output)

# print(f"\nSuccessfully fixed {updated} date ranges.")
