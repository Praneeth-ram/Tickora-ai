# import json
# import re
# from collections import Counter, defaultdict
# from pathlib import Path

# DATASET = Path("data/intent_dataset_merged.jsonl")

# VALID_INTENTS = {
#     "attendance_records",
#     "attendance_summary",
#     "holiday_lookup",
#     "leave_status",
#     "schedule_lookup",
#     "timesheet_lookup",
#     "wfh_status",
# }

# def normalize(text):
#     return re.sub(r"\s+", " ", text.strip().lower())

# rows = []
# invalid = []
# text_targets = defaultdict(set)
# text_lines = defaultdict(list)

# with DATASET.open("r", encoding="utf-8-sig") as file:
#     for line_number, line in enumerate(file, start=1):
#         if not line.strip():
#             continue

#         try:
#             row = json.loads(line)
#         except json.JSONDecodeError as exc:
#             invalid.append((line_number, f"Invalid JSON: {exc}"))
#             continue

#         text = row.get("text")
#         target = row.get("target")

#         if not isinstance(text, str) or not text.strip():
#             invalid.append((line_number, "Missing or empty text"))
#             continue

#         if not isinstance(target, dict):
#             invalid.append((line_number, "Missing or invalid target"))
#             continue

#         intent = target.get("intent")
#         if intent not in VALID_INTENTS:
#             invalid.append((line_number, f"Invalid intent: {intent!r}"))

#         key = normalize(text)
#         target_key = json.dumps(target, sort_keys=True)

#         text_targets[key].add(target_key)
#         text_lines[key].append((line_number, text, target))
#         rows.append(row)

# intents = Counter(
#     row["target"].get("intent")
#     for row in rows
#     if isinstance(row.get("target"), dict)
# )

# periods = Counter(
#     row["target"].get("period")
#     for row in rows
#     if isinstance(row.get("target"), dict)
#     and row["target"].get("period") is not None
# )

# statuses = Counter(
#     row["target"].get("status")
#     for row in rows
#     if isinstance(row.get("target"), dict)
#     and row["target"].get("status") is not None
# )

# duplicates = {
#     key: entries
#     for key, entries in text_lines.items()
#     if len(entries) > 1
# }

# conflicts = {
#     key: entries
#     for key, entries in text_lines.items()
#     if len(text_targets[key]) > 1
# }

# print("=" * 60)
# print("TICKORA AI DATASET AUDIT")
# print("=" * 60)
# print(f"Dataset: {DATASET}")
# print(f"Validly parsed examples: {len(rows)}")
# print(f"Unique normalized questions: {len(text_lines)}")
# print(f"Duplicate question groups: {len(duplicates)}")
# print(f"Conflicting-label groups: {len(conflicts)}")
# print(f"Invalid records: {len(invalid)}")

# print("\nINTENT DISTRIBUTION")
# for intent, count in sorted(intents.items()):
#     print(f"{intent:24} {count:4} ({count / max(len(rows), 1):.1%})")

# print("\nPERIOD DISTRIBUTION")
# for period, count in sorted(periods.items()):
#     print(f"{period:24} {count:4}")

# print("\nSTATUS DISTRIBUTION")
# for status, count in sorted(statuses.items()):
#     print(f"{status:24} {count:4}")

# print("\nCONFLICTING QUESTIONS")
# for key, entries in list(conflicts.items())[:30]:
#     print(f"\nQuestion: {entries[0][1]}")
#     for line_number, text, target in entries:
#         print(f"  Line {line_number}: {target}")

# print("\nDUPLICATE QUESTIONS WITH IDENTICAL TARGETS")
# identical_duplicates = {
#     key: entries for key, entries in duplicates.items()
#     if key not in conflicts
# }
# for key, entries in list(identical_duplicates.items())[:20]:
#     print(f"\nQuestion: {entries[0][1]}")
#     print(f"  Occurrences: {len(entries)}")

# print("\nINVALID RECORDS")
# for line_number, message in invalid[:50]:
#     print(f"Line {line_number}: {message}")

# print("\nAudit completed. The dataset was not modified.")
