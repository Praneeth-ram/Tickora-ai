# import json
# import shutil
# from pathlib import Path

# path = Path("data/intent_dataset_expansion.jsonl")
# backup = Path("data/intent_dataset_expansion.before_wfh_fix.jsonl")

# question = "Tell me whether my latest WFH request was approved"
# replacement = "Check the status of my latest WFH request"

# if not path.exists():
#     raise SystemExit(f"File not found: {path}")

# if not backup.exists():
#     shutil.copy2(path, backup)
#     print(f"Backup created: {backup}")

# rows = []
# updated = 0

# with path.open("r", encoding="utf-8-sig") as file:
#     for line in file:
#         if not line.strip():
#             continue

#         row = json.loads(line)

#         if row.get("text") == question:
#             target = row.get("target", {})

#             if target.get("intent") != "wfh_status":
#                 raise SystemExit(f"Unexpected target: {target}")

#             row["text"] = replacement
#             target.pop("status", None)
#             row["target"] = target
#             updated += 1

#         rows.append(row)

# if updated != 1:
#     raise SystemExit(
#         f"Expected exactly one matching record; found {updated}. "
#         "No changes written."
#     )

# with path.open("w", encoding="utf-8") as file:
#     for row in rows:
#         file.write(json.dumps(row, ensure_ascii=False) + "\n")

# print(f"Updated question: {replacement}")
# print(f"Removed incorrect status label. Intent: wfh_status")
