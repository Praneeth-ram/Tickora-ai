# # import json
# # from pathlib import Path

# # CATALOG_PATH = Path("data/model_catalog.json")
# # OUTPUT_PATH = Path("data/tickora_sft.jsonl")

# # catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
# # ops = {item["operation_id"]: item for item in catalog}

# # SYSTEM = """You are Tickora's query planner.
# # Convert the employee's question into one JSON query plan.
# # Use only the operation IDs and fields in the supplied catalog.
# # Never generate SQL. Never include employee_id or organization_id.
# # Use filters only for supported fields.
# # For date ranges, use {"gte":"YYYY-MM-DD","lte":"YYYY-MM-DD"}.
# # For sums, use aggregate_field.
# # For grouping, use group_by_field and aggregate_function ("count" or "sum").
# # Return a query plan as JSON only.
# # """

# # # Every target below is an explicit, fixed-date or non-relative example.
# # # Add examples only after verifying their expected plans.
# # cases = [
# #     ("Show my attendance records",
# #      {"operation_id":"attendance.list","filters":{}}),
# #     ("List my attendance details",
# #      {"operation_id":"attendance.list","filters":{}}),
# #     ("Show my attendance on 2026-10-12",
# #      {"operation_id":"attendance.list","filters":{"attendance_date":{"gte":"2026-10-12","lte":"2026-10-12"}}}),
# #     ("Show my attendance from 2026-10-01 to 2026-10-15",
# #      {"operation_id":"attendance.list","filters":{"attendance_date":{"gte":"2026-10-01","lte":"2026-10-15"}}}),
# #     ("Show my late attendance records",
# #      {"operation_id":"attendance.list","filters":{"status":"late"}}),
# #     ("Show days when I worked from home",
# #      {"operation_id":"attendance.list","filters":{"work_location":"remote"}}),
# #     ("List my attendance records where I was late",
# #      {"operation_id":"attendance.list","filters":{"is_late":True}}),
# #     ("How many attendance records do I have?",
# #      {"operation_id":"attendance.count","filters":{}}),
# #     ("Count my late attendance records",
# #      {"operation_id":"attendance.count","filters":{"status":"late"}}),
# #     ("Count my attendance from 2026-10-01 to 2026-10-15",
# #      {"operation_id":"attendance.count","filters":{"attendance_date":{"gte":"2026-10-01","lte":"2026-10-15"}}}),
# #     ("How many minutes of overtime did I work?",
# #      {"operation_id":"attendance.sum","aggregate_field":"overtime_minutes","filters":{}}),
# #     ("Calculate my total worked minutes",
# #      {"operation_id":"attendance.sum","aggregate_field":"worked_minutes","filters":{}}),
# #     ("How much overtime did I work between 2026-10-01 and 2026-10-15?",
# #      {"operation_id":"attendance.sum","aggregate_field":"overtime_minutes","filters":{"attendance_date":{"gte":"2026-10-01","lte":"2026-10-15"}}}),
# #     ("Group my attendance by status",
# #      {"operation_id":"attendance.group_by","group_by_field":"status","aggregate_function":"count","filters":{}}),
# #     ("Count attendance records by work location",
# #      {"operation_id":"attendance.group_by","group_by_field":"work_location","aggregate_function":"count","filters":{}}),
# #     ("Sum overtime by attendance status",
# #      {"operation_id":"attendance.group_by","group_by_field":"status","aggregate_function":"sum","aggregate_field":"overtime_minutes","filters":{}}),
# #     ("Show my leave requests",
# #      {"operation_id":"leave_request.list","filters":{}}),
# #     ("Show my pending leave requests",
# #      {"operation_id":"leave_request.list","filters":{"status":"pending"}}),
# #     ("List my approved leave requests",
# #      {"operation_id":"leave_request.list","filters":{"status":"approved"}}),
# #     ("Show my leave requests starting from 2026-10-01",
# #      {"operation_id":"leave_request.list","filters":{"start_date":{"gte":"2026-10-01"}}}),
# #     ("How many leave requests do I have?",
# #      {"operation_id":"leave_request.count","filters":{}}),
# #     ("Count my rejected leave requests",
# #      {"operation_id":"leave_request.count","filters":{"status":"rejected"}}),
# #     ("Show my work from home requests",
# #      {"operation_id":"wfh_request.list","filters":{}}),
# #     ("Show my pending WFH requests",
# #      {"operation_id":"wfh_request.list","filters":{"status":"pending"}}),
# #     ("List my approved work from home requests",
# #      {"operation_id":"wfh_request.list","filters":{"status":"approved"}}),
# #     ("How many WFH requests do I have?",
# #      {"operation_id":"wfh_request.count","filters":{}}),
# #     ("Count my rejected WFH requests",
# #      {"operation_id":"wfh_request.count","filters":{"status":"rejected"}}),
# #     ("Show my timesheets",
# #      {"operation_id":"timesheet.list","filters":{}}),
# #     ("Show my approved timesheets",
# #      {"operation_id":"timesheet.list","filters":{"status":"approved"}}),
# #     ("List my timesheets starting from 2026-10-01",
# #      {"operation_id":"timesheet.list","filters":{"period_start":{"gte":"2026-10-01"}}}),
# #     ("How many timesheets do I have?",
# #      {"operation_id":"timesheet.count","filters":{}}),
# #     ("Count my submitted timesheets",
# #      {"operation_id":"timesheet.count","filters":{"status":"submitted"}}),
# #     ("Show holidays",
# #      {"operation_id":"holiday.list","filters":{}}),
# #     ("Show holidays between 2026-10-01 and 2026-12-31",
# #      {"operation_id":"holiday.list","filters":{"holiday_date":{"gte":"2026-10-01","lte":"2026-12-31"}}}),
# #     ("How many holidays are listed?",
# #      {"operation_id":"holiday.count","filters":{}}),
# # ]

# # def validate_plan(plan):
# #     op_id = plan.get("operation_id")
# #     if op_id not in ops:
# #         raise ValueError(f"Unknown operation: {op_id}")

# #     spec = ops[op_id]
# #     operation = spec["operation"]

# #     allowed_keys = {"operation_id", "filters"}
# #     if operation == "list":
# #         allowed_keys.add("fields")
# #     elif operation == "sum":
# #         allowed_keys.add("aggregate_field")
# #     elif operation == "group_by":
# #         allowed_keys.update({"group_by_field", "aggregate_function"})
# #         if plan.get("aggregate_function") == "sum":
# #             allowed_keys.add("aggregate_field")

# #     extra = set(plan) - allowed_keys
# #     if extra:
# #         raise ValueError(f"{op_id}: unexpected keys {extra}")

# #     fields = plan.get("fields", spec["fields"])
# #     if operation == "list":
# #         if not isinstance(fields, list) or not fields:
# #             raise ValueError(f"{op_id}: fields must be a non-empty list")
# #         if any(f not in spec["fields"] for f in fields):
# #             raise ValueError(f"{op_id}: disallowed list field")
# #     elif "fields" in plan:
# #         raise ValueError(f"{op_id}: fields not allowed")

# #     if operation == "sum":
# #         if plan.get("aggregate_field") not in spec["aggregate_fields"]:
# #             raise ValueError(f"{op_id}: invalid aggregate_field")

# #     if operation == "group_by":
# #         if plan.get("group_by_field") not in spec["group_by_fields"]:
# #             raise ValueError(f"{op_id}: invalid group_by_field")
# #         if plan.get("aggregate_function") not in {"count", "sum"}:
# #             raise ValueError(f"{op_id}: invalid aggregate_function")
# #         if plan["aggregate_function"] == "sum":
# #             if plan.get("aggregate_field") not in spec["aggregate_fields"]:
# #                 raise ValueError(f"{op_id}: invalid grouped aggregate_field")
# #         elif "aggregate_field" in plan:
# #             raise ValueError(f"{op_id}: aggregate_field not allowed for count")

# #     filters = plan.get("filters", {})
# #     if not isinstance(filters, dict):
# #         raise ValueError(f"{op_id}: filters must be an object")
# #     if set(filters) - set(spec["filters"]):
# #         raise ValueError(f"{op_id}: unsupported filter field")

# #     for field, value in filters.items():
# #         if isinstance(value, dict):
# #             if field != spec["date_field"] or not value:
# #                 raise ValueError(f"{op_id}: invalid range filter")
# #             if set(value) - {"gte", "lte"}:
# #                 raise ValueError(f"{op_id}: invalid range operator")
# #             if not all(isinstance(v, str) for v in value.values()):
# #                 raise ValueError(f"{op_id}: date bounds must be strings")
# #         elif value is None or isinstance(value, (dict, list)):
# #             raise ValueError(f"{op_id}: invalid filter value")

# # for question, plan in cases:
# #     validate_plan(plan)

# # OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
# # with OUTPUT_PATH.open("w", encoding="utf-8") as f:
# #     for question, plan in cases:
# #         row = {
# #             "messages": [
# #                 {"role":"system", "content":SYSTEM},
# #                 {"role":"user", "content":question},
# #                 {"role":"assistant", "content":json.dumps(plan, ensure_ascii=False)}
# #             ]
# #         }
# #         f.write(json.dumps(row, ensure_ascii=False) + "\n")

# # print(f"Created {len(cases)} validated examples: {OUTPUT_PATH}")
# # print("Note: this is a starter dataset, not enough for production fine-tuning.")

# """Build and validate Tickora SFT examples against the live model catalog.

# Run from the Tickora-ai repository root:
#     python scripts/build_tickora_dataset.py

# This validates the examples against the same structural query-plan contract as
# backend.services.dynamic_query_service. It does not prove that filter values
# (e.g. status labels) exist in production data; verify those separately.
# """
# import json
# from datetime import date
# from pathlib import Path

# CATALOG_PATH = Path("data/model_catalog.json")
# OUTPUT_PATH = Path("data/tickora_sft.jsonl")

# catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
# ops = {item["operation_id"]: item for item in catalog}

# SYSTEM_PREFIX = """You are Tickora's query planner.
# Convert the employee's question into exactly one JSON query plan.
# Use only operation IDs, fields, filters, aggregate fields, and grouping fields
# from the catalog below. The catalog is authoritative for this request.

# Rules:
# - Never generate SQL.
# - Never include employee_id, organization_id, tenant_id, schema names, or table names.
# - Use only the exact operation_id shown in the catalog.
# - Use only filters listed for that operation.
# - Omit filters that the user did not ask for; use "filters": {} when none apply.
# - For a date filter, a scalar ISO date is an equality filter. For a date range,
#   use {"gte":"YYYY-MM-DD","lte":"YYYY-MM-DD"}; one-sided ranges may use only
#   "gte" or only "lte". Date-range objects are allowed only on that operation's
#   date_field. Do not invent dates for words such as "today" unless the runtime
#   supplies a reference date.
# - For list operations, "fields" may be omitted to use all catalog-approved list
#   fields. If specifying fields, use a non-empty list of approved field names.
# - For sum operations, provide "aggregate_field".
# - For group_by operations, provide "group_by_field" and "aggregate_function"
#   ("count" or "sum"). If aggregate_function is "sum", also provide
#   "aggregate_field". If it is "count", do not provide aggregate_field.
# - Do not add keys that are not part of the query-plan contract.
# - Return JSON only, with no Markdown or explanation.

# Approved operation catalog (JSON):
# """

# SYSTEM = SYSTEM_PREFIX + json.dumps(catalog, ensure_ascii=False, separators=(",", ":"))

# # These examples retain the original fixed dates and labels. Structural
# # validation is strict; production status/location labels must still be verified.
# cases = [
#     ("Show my attendance records", {"operation_id":"attendance.list","filters":{}}),
#     ("List my attendance details", {"operation_id":"attendance.list","filters":{}}),
#     ("Show my attendance on 2026-10-12", {"operation_id":"attendance.list","filters":{"attendance_date":{"gte":"2026-10-12","lte":"2026-10-12"}}}),
#     ("Show my attendance from 2026-10-01 to 2026-10-15", {"operation_id":"attendance.list","filters":{"attendance_date":{"gte":"2026-10-01","lte":"2026-10-15"}}}),
#     ("Show my late attendance records", {"operation_id":"attendance.list","filters":{"status":"late"}}),
#     ("Show days when I worked from home", {"operation_id":"attendance.list","filters":{"work_location":"remote"}}),
#     ("List my attendance records where I was late", {"operation_id":"attendance.list","filters":{"is_late":True}}),
#     ("How many attendance records do I have?", {"operation_id":"attendance.count","filters":{}}),
#     ("Count my late attendance records", {"operation_id":"attendance.count","filters":{"status":"late"}}),
#     ("Count my attendance from 2026-10-01 to 2026-10-15", {"operation_id":"attendance.count","filters":{"attendance_date":{"gte":"2026-10-01","lte":"2026-10-15"}}}),
#     ("How many minutes of overtime did I work?", {"operation_id":"attendance.sum","aggregate_field":"overtime_minutes","filters":{}}),
#     ("Calculate my total worked minutes", {"operation_id":"attendance.sum","aggregate_field":"worked_minutes","filters":{}}),
#     ("How much overtime did I work between 2026-10-01 and 2026-10-15?", {"operation_id":"attendance.sum","aggregate_field":"overtime_minutes","filters":{"attendance_date":{"gte":"2026-10-01","lte":"2026-10-15"}}}),
#     ("Group my attendance by status", {"operation_id":"attendance.group_by","group_by_field":"status","aggregate_function":"count","filters":{}}),
#     ("Count attendance records by work location", {"operation_id":"attendance.group_by","group_by_field":"work_location","aggregate_function":"count","filters":{}}),
#     ("Sum overtime by attendance status", {"operation_id":"attendance.group_by","group_by_field":"status","aggregate_function":"sum","aggregate_field":"overtime_minutes","filters":{}}),
#     ("Show my leave requests", {"operation_id":"leave_request.list","filters":{}}),
#     ("Show my pending leave requests", {"operation_id":"leave_request.list","filters":{"status":"pending"}}),
#     ("List my approved leave requests", {"operation_id":"leave_request.list","filters":{"status":"approved"}}),
#     ("Show my leave requests starting from 2026-10-01", {"operation_id":"leave_request.list","filters":{"start_date":{"gte":"2026-10-01"}}}),
#     ("How many leave requests do I have?", {"operation_id":"leave_request.count","filters":{}}),
#     ("Count my rejected leave requests", {"operation_id":"leave_request.count","filters":{"status":"rejected"}}),
#     ("Show my work from home requests", {"operation_id":"wfh_request.list","filters":{}}),
#     ("Show my pending WFH requests", {"operation_id":"wfh_request.list","filters":{"status":"pending"}}),
#     ("List my approved work from home requests", {"operation_id":"wfh_request.list","filters":{"status":"approved"}}),
#     ("How many WFH requests do I have?", {"operation_id":"wfh_request.count","filters":{}}),
#     ("Count my rejected WFH requests", {"operation_id":"wfh_request.count","filters":{"status":"rejected"}}),
#     ("Show my timesheets", {"operation_id":"timesheet.list","filters":{}}),
#     ("Show my approved timesheets", {"operation_id":"timesheet.list","filters":{"status":"approved"}}),
#     ("List my timesheets starting from 2026-10-01", {"operation_id":"timesheet.list","filters":{"period_start":{"gte":"2026-10-01"}}}),
#     ("How many timesheets do I have?", {"operation_id":"timesheet.count","filters":{}}),
#     ("Count my submitted timesheets", {"operation_id":"timesheet.count","filters":{"status":"submitted"}}),
#     ("Show holidays", {"operation_id":"holiday.list","filters":{}}),
#     ("Show holidays between 2026-10-01 and 2026-12-31", {"operation_id":"holiday.list","filters":{"holiday_date":{"gte":"2026-10-01","lte":"2026-12-31"}}}),
#     ("How many holidays are listed?", {"operation_id":"holiday.count","filters":{}}),
# ]

# def validate_plan(plan):
#     if not isinstance(plan, dict):
#         raise ValueError("plan must be an object")
#     op_id = plan.get("operation_id")
#     if not isinstance(op_id, str) or op_id not in ops:
#         raise ValueError(f"Unknown operation: {op_id!r}")

#     spec = ops[op_id]
#     operation = spec["operation"]

#     allowed_keys = {"operation_id", "filters"}
#     if operation == "list":
#         allowed_keys.add("fields")
#     elif operation == "count":
#         pass
#     elif operation == "sum":
#         allowed_keys.add("aggregate_field")
#     elif operation == "group_by":
#         allowed_keys.update({"group_by_field", "aggregate_function"})
#         if plan.get("aggregate_function") == "sum":
#             allowed_keys.add("aggregate_field")
#     else:
#         raise ValueError(f"{op_id}: unsupported operation {operation!r}")

#     extra = set(plan) - allowed_keys
#     if extra:
#         raise ValueError(f"{op_id}: unexpected keys {sorted(extra)}")

#     if operation == "list":
#         fields = plan.get("fields", spec["fields"])
#         if not isinstance(fields, list) or not fields:
#             raise ValueError(f"{op_id}: fields must be a non-empty list when specified")
#         if any(not isinstance(f, str) or f not in spec["fields"] for f in fields):
#             raise ValueError(f"{op_id}: disallowed list field")
#     elif "fields" in plan:
#         raise ValueError(f"{op_id}: fields not allowed")

#     if operation == "sum":
#         if plan.get("aggregate_field") not in spec.get("aggregate_fields", []):
#             raise ValueError(f"{op_id}: invalid aggregate_field")

#     if operation == "group_by":
#         if plan.get("group_by_field") not in spec.get("group_by_fields", []):
#             raise ValueError(f"{op_id}: invalid group_by_field")
#         if plan.get("aggregate_function") not in {"count", "sum"}:
#             raise ValueError(f"{op_id}: invalid aggregate_function")
#         if plan["aggregate_function"] == "sum":
#             if plan.get("aggregate_field") not in spec.get("aggregate_fields", []):
#                 raise ValueError(f"{op_id}: invalid grouped aggregate_field")
#         elif "aggregate_field" in plan:
#             raise ValueError(f"{op_id}: aggregate_field not allowed for grouped count")

#     filters = plan.get("filters", {})
#     if not isinstance(filters, dict):
#         raise ValueError(f"{op_id}: filters must be an object")
#     if any(not isinstance(k, str) for k in filters):
#         raise ValueError(f"{op_id}: filter keys must be strings")
#     if set(filters) - set(spec["filters"]):
#         raise ValueError(f"{op_id}: unsupported filter field")

#     for field, value in filters.items():
#         if isinstance(value, dict):
#             if field != spec.get("date_field") or not value:
#                 raise ValueError(f"{op_id}: range filter must target date_field and not be empty")
#             if set(value) - {"gte", "lte"}:
#                 raise ValueError(f"{op_id}: date range accepts only gte/lte")
#             parsed = {}
#             for bound, raw in value.items():
#                 if not isinstance(raw, str):
#                     raise ValueError(f"{op_id}: {field}.{bound} must be an ISO date string")
#                 try:
#                     parsed[bound] = date.fromisoformat(raw)
#                 except ValueError as exc:
#                     raise ValueError(f"{op_id}: {field}.{bound} must be YYYY-MM-DD") from exc
#                 if parsed[bound].isoformat() != raw:
#                     raise ValueError(f"{op_id}: {field}.{bound} must be YYYY-MM-DD")
#             if "gte" in parsed and "lte" in parsed and parsed["gte"] > parsed["lte"]:
#                 raise ValueError(f"{op_id}: date range start must not be after end")
#         else:
#             if value is None or isinstance(value, (dict, list)):
#                 raise ValueError(f"{op_id}: invalid filter value for {field}")
#             if isinstance(value, float):
#                 import math
#                 if not math.isfinite(value):
#                     raise ValueError(f"{op_id}: non-finite number for {field}")
#             if isinstance(value, str) and len(value) > 200:
#                 raise ValueError(f"{op_id}: filter value too long for {field}")
#             if not isinstance(value, (str, int, float, bool)):
#                 raise ValueError(f"{op_id}: unsupported filter value type for {field}")

# for question, plan in cases:
#     validate_plan(plan)

# OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
# with OUTPUT_PATH.open("w", encoding="utf-8") as f:
#     for question, plan in cases:
#         row = {
#             "messages": [
#                 {"role": "system", "content": SYSTEM},
#                 {"role": "user", "content": question},
#                 {"role": "assistant", "content": json.dumps(plan, ensure_ascii=False, separators=(",", ":"))},
#             ]
#         }
#         f.write(json.dumps(row, ensure_ascii=False) + "\n")

# print(f"Created {len(cases)} validated examples: {OUTPUT_PATH}")
# print(f"Catalog operations included in every system message: {len(ops)}")
# print("Important: this is still a small starter dataset, not production-ready training data.")
# print("Verify status/location enum values against your real database before training.")

"""Build a larger Tickora SFT dataset from the live operation catalog.

Run from the Tickora-ai repository root:
    python scripts/build_tickora_dataset.py

The generated plans are checked against the structural contract used by
backend.services.dynamic_query_service. Status/location labels below are based
on values observed in the user's development database; observed values may not
be exhaustive of all values the application permits.
"""
import json
import math
from datetime import date
from pathlib import Path

CATALOG_PATH = Path("data/model_catalog.json")
OUTPUT_PATH = Path("data/tickora_sft.jsonl")

catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
ops = {item["operation_id"]: item for item in catalog}

SYSTEM_PREFIX = """You are Tickora's query planner.
Convert the employee's question into exactly one JSON query plan.
Use only operation IDs, fields, filters, aggregate fields, and grouping fields
from the catalog below. The catalog is authoritative for this request.

Rules:
- Never generate SQL.
- Never include employee_id, organization_id, tenant_id, schema names, or table names.
- Use the exact operation_id shown in the catalog.
- Use only filters listed for that operation.
- Omit filters the user did not ask for; include "filters": {} when none apply.
- For a date filter, an ISO date string means equality. For a date range, use
  {"gte":"YYYY-MM-DD","lte":"YYYY-MM-DD"}. One-sided ranges may use only gte
  or only lte. Range objects are allowed only on the operation's date_field.
- Do not invent dates for relative terms like today or this month unless a
  reference date is explicitly provided in the request context.
- For list operations, omit fields to request the catalog's approved default
  fields. If fields are specified, use a non-empty list of approved fields.
- For sum operations, provide aggregate_field.
- For group_by operations, provide group_by_field and aggregate_function
  ("count" or "sum"). If aggregate_function is "sum", also provide
  aggregate_field. If it is "count", do not provide aggregate_field.
- Do not add unapproved keys.
- Return JSON only, with no Markdown or explanation.

Approved operation catalog (JSON):
"""
SYSTEM = SYSTEM_PREFIX + json.dumps(catalog, ensure_ascii=False, separators=(",", ":"))

# These are observed development-database values. They should be refreshed if
# application enums change. Avoid assuming an observed set is exhaustive.
ATTENDANCE_STATUSES = ["absent", "half_day", "late", "on_leave", "present"]
WORK_LOCATIONS = ["office", "remote", "work_from_home"]
LEAVE_STATUSES = ["approved", "cancelled", "pending", "rejected"]
TIMESHEET_STATUSES = ["approved", "draft", "rejected", "submitted"]
WFH_STATUSES = ["approved", "cancelled", "pending", "rejected"]

DATE_RANGES = [
    ("2026-10-01", "2026-10-07"),
    ("2026-10-01", "2026-10-15"),
    ("2026-10-01", "2026-10-31"),
    ("2026-09-01", "2026-09-30"),
]

# Each base case has six phrasings. This creates variation without randomly
# combining fields or inventing unsupported operation names.
cases = []

def add_variants(plan, phrases):
    for question in phrases:
        cases.append((question, dict(plan)))

def add_filter_variants(op_id, filter_name, value, nouns, verbs=None):
    plan = {"operation_id": op_id, "filters": {filter_name: value}}
    if op_id.endswith(".count"):
        phrases = [
            f"Count my {nouns}",
            f"How many {nouns} are there?",
            f"Give me the number of {nouns}",
            f"What is the count of {nouns}?",
            f"Calculate the number of {nouns}",
            f"Return a count for {nouns}",
        ]
    else:
        phrases = [
            f"Show my {nouns}",
            f"List my {nouns}",
            f"Can you find my {nouns}?",
            f"I want to see my {nouns}",
            f"Please display my {nouns}",
            f"Retrieve my {nouns} for me",
        ]
    add_variants(plan, phrases)

def add_date_range_variants(op_id, date_field, start, end, noun):
    value = {"gte": start, "lte": end}
    plan = {"operation_id": op_id, "filters": {date_field: value}}
    if op_id.endswith(".count"):
        phrases = [
            f"Count my {noun} from {start} through {end}",
            f"How many {noun} are there between {start} and {end}?",
            f"Give me the number of {noun} from {start} to {end}",
            f"What is the count of {noun} for {start} through {end}?",
            f"Calculate the number of {noun} dated between {start} and {end}",
            f"Return a count of {noun} covering {start} to {end}",
        ]
    else:
        phrases = [
            f"Show my {noun} from {start} through {end}",
            f"List my {noun} between {start} and {end}",
            f"Find my {noun} from {start} to {end}",
            f"Display my {noun} for {start} through {end}",
            f"Get my {noun} dated between {start} and {end}",
            f"Retrieve my {noun} covering {start} to {end}",
        ]
    add_variants(plan, phrases)

def add_one_sided_variants(op_id, date_field, bound, value, noun):
    plan = {"operation_id": op_id, "filters": {date_field: {bound: value}}}
    if bound == "gte":
        phrases = [
            f"Show my {noun} starting on {value}",
            f"List my {noun} from {value} onward",
            f"Find my {noun} beginning {value}",
            f"Display my {noun} on or after {value}",
            f"Get my {noun} starting from {value}",
            f"Retrieve my {noun} dated {value} or later",
        ]
    else:
        phrases = [
            f"Show my {noun} through {value}",
            f"List my {noun} up to {value}",
            f"Find my {noun} on or before {value}",
            f"Display my {noun} no later than {value}",
            f"Get my {noun} ending by {value}",
            f"Retrieve my {noun} dated {value} or earlier",
        ]
    add_variants(plan, phrases)

# Attendance list: general, statuses, work locations, boolean late flag, dates.
add_variants({"operation_id":"attendance.list","filters":{}}, [
    "Show my attendance records", "List my attendance details",
    "Can I see my attendance history?", "Display my attendance records",
    "Retrieve my attendance entries", "I want to view my attendance",
])
for status in ATTENDANCE_STATUSES:
    add_filter_variants("attendance.list", "status", status, f"{status.replace('_',' ')} attendance records")
for location in WORK_LOCATIONS:
    add_filter_variants("attendance.list", "work_location", location, f"attendance records for {location.replace('_',' ')} work")
add_variants({"operation_id":"attendance.list","filters":{"is_late":True}}, [
    "Show attendance records where the late flag is enabled",
    "Find attendance entries explicitly flagged as late",
    "Display attendance records with is_late set to true",
    "Get my attendance records with a true late flag",
    "List attendance entries where the late flag is true",
    "Retrieve records whose late indicator is enabled",
])
for start, end in DATE_RANGES:
    add_date_range_variants("attendance.list", "attendance_date", start, end, "attendance records")
add_one_sided_variants("attendance.list", "attendance_date", "gte", "2026-10-01", "attendance records")
add_one_sided_variants("attendance.list", "attendance_date", "lte", "2026-10-31", "attendance records")

# Attendance count.
add_variants({"operation_id":"attendance.count","filters":{}}, [
    "How many attendance records do I have?", "Count my attendance entries",
    "Give me the number of my attendance records", "What is my attendance record count?",
    "Calculate how many attendance records are available for me", "Count all my attendance records",
])
for status in ATTENDANCE_STATUSES:
    add_filter_variants("attendance.count", "status", status, f"{status.replace('_',' ')} attendance records", ["Count", "Count", "Find", "Count", "Calculate", "Count"])
for location in WORK_LOCATIONS:
    add_filter_variants("attendance.count", "work_location", location, f"attendance records for {location.replace('_',' ')} work", ["Count", "Count", "Find", "Count", "Calculate", "Count"])
for start, end in DATE_RANGES[:3]:
    add_date_range_variants("attendance.count", "attendance_date", start, end, "attendance records")
add_variants({"operation_id":"attendance.count","filters":{"is_late":True}}, [
    "Count attendance records where the late flag is enabled",
    "How many attendance records have the late flag set to true?",
    "Count attendance entries with the late flag enabled",
    "Give me the number of records with a true late indicator",
    "Calculate the count of attendance records where is_late is true",
    "How many attendance records have is_late set to true?",
])

# Attendance sums.
for field, label in [("worked_minutes","worked minutes"),("overtime_minutes","overtime minutes")]:
    add_variants({"operation_id":"attendance.sum","aggregate_field":field,"filters":{}}, [
        f"Calculate my total {label}", f"What is my total {label}?",
        f"Sum my {label}", f"How many {label} have I accumulated?",
        f"Give me the sum of my {label}", f"Compute the total of my {label}",
    ])
    for start, end in DATE_RANGES[:3]:
        add_variants({"operation_id":"attendance.sum","aggregate_field":field,"filters":{"attendance_date":{"gte":start,"lte":end}}}, [
            f"Calculate my {label} from {start} through {end}",
            f"Sum my {label} between {start} and {end}",
            f"What is my total {label} for {start} to {end}?",
            f"Get the sum of my {label} dated {start} through {end}",
            f"Compute my {label} from {start} to {end}",
            f"How much {label} did I record between {start} and {end}?",
        ])

# Attendance grouping: each supported grouping field, counts and sums.
for group_field, group_label in [("status","status"),("work_location","work location"),("is_late","late flag")]:
    add_variants({"operation_id":"attendance.group_by","group_by_field":group_field,"aggregate_function":"count","filters":{}}, [
        f"Group my attendance by {group_label}", f"Count my attendance records grouped by {group_label}",
        f"Show attendance counts for each {group_label}", f"Break down my attendance by {group_label}",
        f"Give me a {group_label} wise count of attendance", f"Summarize my attendance record count by {group_label}",
    ])
    for field, label in [("worked_minutes","worked minutes"),("overtime_minutes","overtime minutes")]:
        add_variants({"operation_id":"attendance.group_by","group_by_field":group_field,"aggregate_function":"sum","aggregate_field":field,"filters":{}}, [
            f"Sum {label} grouped by {group_label}", f"Group my {label} totals by {group_label}",
            f"Show total {label} for each {group_label}", f"Break down summed {label} by {group_label}",
            f"Calculate {label} totals per {group_label}", f"Give me a grouped sum of {label} by {group_label}",
        ])

# Leave requests.
add_variants({"operation_id":"leave_request.list","filters":{}}, [
    "Show my leave requests", "List my leave applications",
    "Display all my leave requests", "Can I see my leave request history?",
    "Retrieve my leave applications", "I want to view my leave requests",
])
for status in LEAVE_STATUSES:
    add_filter_variants("leave_request.list", "status", status, f"{status} leave requests")
for start, end in DATE_RANGES:
    add_date_range_variants("leave_request.list", "start_date", start, end, "leave requests starting")
add_one_sided_variants("leave_request.list", "start_date", "gte", "2026-10-01", "leave requests")
add_one_sided_variants("leave_request.list", "start_date", "lte", "2026-10-31", "leave requests")
add_variants({"operation_id":"leave_request.count","filters":{}}, [
    "How many leave requests do I have?", "Count my leave applications",
    "Give me the total number of leave requests", "What is my leave request count?",
    "Calculate the number of leave applications I have", "Count all my leave requests",
])
for status in LEAVE_STATUSES:
    add_filter_variants("leave_request.count", "status", status, f"{status} leave requests", ["Count", "Count", "Find", "Count", "Calculate", "Count"])
for start, end in DATE_RANGES[:3]:
    add_date_range_variants("leave_request.count", "start_date", start, end, "leave requests")

# WFH requests.
add_variants({"operation_id":"wfh_request.list","filters":{}}, [
    "Show my work from home requests", "List my WFH requests",
    "Display my work-from-home applications", "Can I see my WFH request history?",
    "Retrieve my remote-work requests", "I want to view my work from home requests",
])
for status in WFH_STATUSES:
    add_filter_variants("wfh_request.list", "status", status, f"{status} WFH requests")
for start, end in DATE_RANGES:
    add_date_range_variants("wfh_request.list", "start_date", start, end, "WFH requests")
add_one_sided_variants("wfh_request.list", "start_date", "gte", "2026-10-01", "WFH requests")
add_one_sided_variants("wfh_request.list", "start_date", "lte", "2026-10-31", "WFH requests")
add_variants({"operation_id":"wfh_request.count","filters":{}}, [
    "How many WFH requests do I have?", "Count my work from home requests",
    "Give me the total number of WFH requests", "What is my work-from-home request count?",
    "Calculate how many remote-work requests I have", "Count all my WFH applications",
])
for status in WFH_STATUSES:
    add_filter_variants("wfh_request.count", "status", status, f"{status} WFH requests", ["Count", "Count", "Find", "Count", "Calculate", "Count"])
for start, end in DATE_RANGES[:3]:
    add_date_range_variants("wfh_request.count", "start_date", start, end, "WFH requests")

# Timesheets.
add_variants({"operation_id":"timesheet.list","filters":{}}, [
    "Show my timesheets", "List my timesheet records",
    "Display my timesheet history", "Can I see my timesheets?",
    "Retrieve my timesheet entries", "I want to view my timesheets",
])
for status in TIMESHEET_STATUSES:
    add_filter_variants("timesheet.list", "status", status, f"{status} timesheets")
for start, end in DATE_RANGES:
    add_date_range_variants("timesheet.list", "period_start", start, end, "timesheets")
add_one_sided_variants("timesheet.list", "period_start", "gte", "2026-10-01", "timesheets")
add_one_sided_variants("timesheet.list", "period_start", "lte", "2026-10-31", "timesheets")
add_variants({"operation_id":"timesheet.count","filters":{}}, [
    "How many timesheets do I have?", "Count my timesheets",
    "Give me the total number of timesheet records", "What is my timesheet count?",
    "Calculate how many timesheets I have", "Count all my timesheet entries",
])
for status in TIMESHEET_STATUSES:
    add_filter_variants("timesheet.count", "status", status, f"{status} timesheets", ["Count", "Count", "Find", "Count", "Calculate", "Count"])
for start, end in DATE_RANGES[:3]:
    add_date_range_variants("timesheet.count", "period_start", start, end, "timesheets")

# Holidays.
add_variants({"operation_id":"holiday.list","filters":{}}, [
    "Show holidays", "List the holidays", "Display the holiday calendar",
    "What holidays are listed?", "Retrieve the holiday list", "I want to see the holidays",
])
for start, end in DATE_RANGES:
    add_date_range_variants("holiday.list", "holiday_date", start, end, "holidays")
add_variants({"operation_id":"holiday.count","filters":{}}, [
    "How many holidays are listed?", "Count the holidays",
    "Give me the number of holidays", "What is the holiday count?",
    "Calculate the total number of holidays", "Count all listed holidays",
])
for start, end in DATE_RANGES:
    add_date_range_variants("holiday.count", "holiday_date", start, end, "holidays")

def validate_plan(plan):
    if not isinstance(plan, dict):
        raise ValueError("plan must be an object")
    op_id = plan.get("operation_id")
    if not isinstance(op_id, str) or op_id not in ops:
        raise ValueError(f"Unknown operation: {op_id!r}")
    spec = ops[op_id]
    operation = spec["operation"]

    allowed_keys = {"operation_id", "filters"}
    if operation == "list":
        allowed_keys.add("fields")
    elif operation == "count":
        pass
    elif operation == "sum":
        allowed_keys.add("aggregate_field")
    elif operation == "group_by":
        allowed_keys.update({"group_by_field", "aggregate_function"})
        if plan.get("aggregate_function") == "sum":
            allowed_keys.add("aggregate_field")
    else:
        raise ValueError(f"{op_id}: unsupported operation {operation!r}")

    extra = set(plan) - allowed_keys
    if extra:
        raise ValueError(f"{op_id}: unexpected keys {sorted(extra)}")

    if operation == "list":
        fields = plan.get("fields", spec["fields"])
        if not isinstance(fields, list) or not fields:
            raise ValueError(f"{op_id}: fields must be a non-empty list when specified")
        if any(not isinstance(f, str) or f not in spec["fields"] for f in fields):
            raise ValueError(f"{op_id}: disallowed list field")

    if operation == "sum" and plan.get("aggregate_field") not in spec.get("aggregate_fields", []):
        raise ValueError(f"{op_id}: invalid aggregate_field")

    if operation == "group_by":
        if plan.get("group_by_field") not in spec.get("group_by_fields", []):
            raise ValueError(f"{op_id}: invalid group_by_field")
        if plan.get("aggregate_function") not in {"count", "sum"}:
            raise ValueError(f"{op_id}: invalid aggregate_function")
        if plan["aggregate_function"] == "sum":
            if plan.get("aggregate_field") not in spec.get("aggregate_fields", []):
                raise ValueError(f"{op_id}: invalid grouped aggregate_field")
        elif "aggregate_field" in plan:
            raise ValueError(f"{op_id}: aggregate_field not allowed for grouped count")

    filters = plan.get("filters", {})
    if not isinstance(filters, dict):
        raise ValueError(f"{op_id}: filters must be an object")
    if set(filters) - set(spec["filters"]):
        raise ValueError(f"{op_id}: unsupported filter field")

    for field, value in filters.items():
        if isinstance(value, dict):
            if field != spec.get("date_field") or not value:
                raise ValueError(f"{op_id}: range filter must target date_field and not be empty")
            if set(value) - {"gte", "lte"}:
                raise ValueError(f"{op_id}: date range accepts only gte/lte")
            parsed = {}
            for bound, raw in value.items():
                if not isinstance(raw, str):
                    raise ValueError(f"{op_id}: {field}.{bound} must be an ISO date string")
                try:
                    parsed[bound] = date.fromisoformat(raw)
                except ValueError as exc:
                    raise ValueError(f"{op_id}: {field}.{bound} must be YYYY-MM-DD") from exc
                if parsed[bound].isoformat() != raw:
                    raise ValueError(f"{op_id}: {field}.{bound} must be YYYY-MM-DD")
            if "gte" in parsed and "lte" in parsed and parsed["gte"] > parsed["lte"]:
                raise ValueError(f"{op_id}: date range start must not be after end")
        else:
            if value is None or isinstance(value, (dict, list)):
                raise ValueError(f"{op_id}: invalid filter value for {field}")
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(f"{op_id}: non-finite number for {field}")
            if isinstance(value, str) and len(value) > 200:
                raise ValueError(f"{op_id}: filter value too long for {field}")
            if not isinstance(value, (str, int, float, bool)):
                raise ValueError(f"{op_id}: unsupported filter value type for {field}")

# Expand each validated plan with additional natural-language paraphrases.
# These paraphrases are plan-aware; they do not invent catalog operations or values.
def _human_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).replace("_", " ")

_ENTITY_WORDS = {
    "attendance": "attendance records",
    "holiday": "holidays",
    "leave_request": "leave requests",
    "wfh_request": "work-from-home requests",
    "timesheet": "timesheets",
}
_FIELD_WORDS = {
    "worked_minutes": "worked minutes",
    "overtime_minutes": "overtime minutes",
    "status": "status",
    "work_location": "work location",
    "is_late": "late flag",
}

def _plan_descriptors(plan):
    descriptors = []
    filters = plan.get("filters", {})
    for field, value in filters.items():
        if isinstance(value, dict):
            if "gte" in value and "lte" in value:
                descriptors.append(f"from {value['gte']} through {value['lte']}")
            elif "gte" in value:
                descriptors.append(f"on or after {value['gte']}")
            elif "lte" in value:
                descriptors.append(f"on or before {value['lte']}")
        elif field == "status":
            descriptors.append(f"with status recorded as {_human_value(value)}")
        elif field == "work_location":
            descriptors.append(f"with work location set to {_human_value(value)}")
        elif field == "is_late":
            descriptors.append(f"where the late flag is {_human_value(value)}")
        else:
            descriptors.append(f"where {field.replace('_', ' ')} is {_human_value(value)}")
    return descriptors

def _extra_phrases(plan):
    op_id = plan["operation_id"]
    spec = ops[op_id]
    entity = _ENTITY_WORDS[spec["entity"]]
    operation = spec["operation"]
    desc = " ".join(_plan_descriptors(plan)).strip()
    subject = entity if not desc else f"{entity} {desc}"
    phrases = []

    if operation == "list":
        phrases += [
            f"Please show {subject}.",
            f"I need to view {subject}.",
            f"Can you display {subject}?",
            f"Fetch {subject} for me.",
            f"I'd like to review {subject}.",
            f"Bring up {subject}.",
            f"Find {subject}.",
            f"Show me {subject} in the system.",
        ]
    elif operation == "count":
        phrases += [
            f"What is the total count of {subject}?",
            f"Please count {subject}.",
            f"Tell me how many {subject} exist.",
            f"Return the number of {subject}.",
            f"Could you calculate the count of {subject}?",
            f"I need a count of {subject}.",
            f"Report how many {subject} there are.",
            f"What number of {subject} do I have?" if spec["entity"] != "holiday" else f"What number of {subject} are listed?",
        ]
    elif operation == "sum":
        field = plan["aggregate_field"]
        metric = _FIELD_WORDS.get(field, field.replace("_", " "))
        metric_subject = f"{metric} for {subject}"
        phrases += [
            f"What is the total {metric_subject}?",
            f"Calculate the sum of {metric_subject}.",
            f"Please add up the {metric_subject}.",
            f"How much {metric} is recorded for {subject}?",
            f"Return the aggregate total of {metric_subject}.",
            f"Compute the overall {metric_subject}.",
            f"I need the sum of {metric_subject}.",
            f"Give me a total for {metric_subject}.",
        ]
    elif operation == "group_by":
        group_field = plan["group_by_field"]
        group_label = _FIELD_WORDS.get(group_field, group_field.replace("_", " "))
        if plan["aggregate_function"] == "count":
            phrases += [
                f"Break down the count of {subject} by {group_label}.",
                f"Show a count grouped by {group_label} for {subject}.",
                f"How are {subject} distributed by {group_label}?",
                f"Give me counts per {group_label} for {subject}.",
                f"Summarize {subject} by {group_label} using counts.",
                f"Create a count breakdown of {subject} by {group_label}.",
                f"Count each {group_label} group for {subject}.",
                f"Show the number of {subject} in each {group_label} group.",
            ]
        else:
            metric = _FIELD_WORDS.get(plan["aggregate_field"], plan["aggregate_field"].replace("_", " "))
            phrases += [
                f"Sum {metric} for {subject}, grouped by {group_label}.",
                f"Show {metric} totals by {group_label} for {subject}.",
                f"Calculate grouped sums of {metric} for {subject} by {group_label}.",
                f"Give me the total {metric} in each {group_label} group for {subject}.",
                f"Aggregate {metric} by {group_label} across {subject}.",
                f"Break down total {metric} for {subject} by {group_label}.",
                f"What is the sum of {metric} per {group_label} for {subject}?",
                f"Return grouped {metric} totals for {subject}.",
            ]
    # Exclude already-used wording; the final global duplicate check catches
    # any cross-plan collisions rather than silently assigning conflicting labels.
    return phrases

# Add paraphrases for every distinct plan, then cap each plan at a balanced number
# of examples. The existing seed phrases are retained.
_seed_by_plan = {}
for _question, _plan in cases:
    _key = json.dumps(_plan, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    _seed_by_plan.setdefault(_key, (_plan, []))[1].append(_question)
for _plan, _seed_questions in _seed_by_plan.values():
    for _question in _extra_phrases(_plan):
        cases.append((_question, dict(_plan)))

# Keep the fixed regression test questions out of the generated train/validation pool.
# The existing test file is retained as the separate final evaluation set.
_FIXED_TEST_PATH = Path("data/splits/test.jsonl")
_fixed_test_questions = set()
if _FIXED_TEST_PATH.exists():
    for _line in _FIXED_TEST_PATH.read_text(encoding="utf-8").splitlines():
        if not _line.strip():
            continue
        _record = json.loads(_line)
        _fixed_test_questions.add(next(m["content"].strip().casefold() for m in _record["messages"] if m["role"] == "user"))

# Deduplicate exact questions and reject conflicting labels. We keep up to 11
# utterances per plan (seed phrases plus paraphrases), so common query patterns
# have useful variation without letting a single plan dominate the corpus.
_plan_variants = {}
for question, plan in cases:
    key = json.dumps(plan, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    _plan_variants.setdefault(key, (plan, []))[1].append(question)

expanded_cases = []
for key, (plan, questions_for_plan) in _plan_variants.items():
    unique_for_plan = []
    seen_for_plan = set()
    for question in questions_for_plan:
        normalized = " ".join(question.casefold().split())
        if normalized not in seen_for_plan:
            seen_for_plan.add(normalized)
            unique_for_plan.append(question)
    # Preserve all original seed examples, plus up to 8 additional paraphrases.
    # Cap is 11 because the seed builder initially supplies up to 3 per plan.
    for question in unique_for_plan[:11]:
        expanded_cases.append((question, plan))

# Remove fixed-test utterances from the generated corpus, then enforce unique
# questions globally. Same plan may appear in train and validation as different
# utterances; exact question leakage is forbidden.
filtered_cases = []
seen_questions = {}
for question, plan in expanded_cases:
    normalized = " ".join(question.casefold().split())
    if normalized in _fixed_test_questions:
        continue
    if normalized in seen_questions:
        if seen_questions[normalized] != plan:
            raise ValueError(f"Question maps to conflicting plans: {question!r}")
        continue
    seen_questions[normalized] = plan
    validate_plan(plan)
    filtered_cases.append((question, plan))

if len(filtered_cases) < 500:
    raise ValueError(f"Expected at least 500 expanded examples, got {len(filtered_cases)}")

# Build complete chat records.
def _record(question, plan):
    return {"messages": [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": question},
        {"role": "assistant", "content": json.dumps(plan, ensure_ascii=False, separators=(",", ":"))},
    ]}

all_records = [_record(q, p) for q, p in filtered_cases]
OUTPUT_PATH = Path("data/tickora_sft_expanded.jsonl")
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
with OUTPUT_PATH.open("w", encoding="utf-8", newline="\n") as file:
    for record in all_records:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")

# Make reproducible train/validation splits by query-plan group so paraphrases of
# one exact plan do not appear in both training and validation. Keep fixed test
# untouched. This is a regression test for unseen wording, not a test of unseen
# plan structures, because the expanded training set intentionally learns those plans.
from collections import defaultdict, Counter
from random import Random

groups = defaultdict(list)
for record in all_records:
    plan = json.loads(record["messages"][-1]["content"])
    key = json.dumps(plan, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    groups[(plan["operation_id"], key)].append(record)

by_operation = defaultdict(list)
for (op_id, plan_key), rows in groups.items():
    by_operation[op_id].append((plan_key, rows))

rng = Random(42)
train_records, validation_records = [], []
for op_id in sorted(by_operation):
    plan_groups = by_operation[op_id]
    rng.shuffle(plan_groups)
    # Reserve approximately 10% of this operation's plan groups for validation,
    # but never move every group out of training.
    n_val = max(1, round(len(plan_groups) * 0.10)) if len(plan_groups) > 1 else 0
    n_val = min(n_val, max(0, len(plan_groups) - 1))
    for i, (_, rows) in enumerate(plan_groups):
        (validation_records if i < n_val else train_records).extend(rows)

rng.shuffle(train_records)
rng.shuffle(validation_records)
SPLIT_DIR = Path("data/splits")
SPLIT_DIR.mkdir(parents=True, exist_ok=True)
for name, rows in [("train.jsonl", train_records), ("validation.jsonl", validation_records)]:
    with (SPLIT_DIR / name).open("w", encoding="utf-8", newline="\n") as file:
        for record in rows:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")

if not _FIXED_TEST_PATH.exists():
    raise FileNotFoundError(
        "A fixed held-out test file is required at data/splits/test.jsonl. "
        "Restore the existing 42-example test file before building the expanded dataset."
    )

# Validate counts, operation coverage, exact question leakage, and split-plan isolation.
def _load_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

check_train = _load_jsonl(SPLIT_DIR / "train.jsonl")
check_val = _load_jsonl(SPLIT_DIR / "validation.jsonl")
check_test = _load_jsonl(_FIXED_TEST_PATH)

def _q(record):
    return next(m["content"].strip().casefold() for m in record["messages"] if m["role"] == "user")
def _plan(record):
    return json.dumps(json.loads(record["messages"][-1]["content"]), sort_keys=True, ensure_ascii=False, separators=(",", ":"))

train_q, val_q, test_q = set(map(_q, check_train)), set(map(_q, check_val)), set(map(_q, check_test))
assert not (train_q & val_q), "Exact question leakage between train and validation"
assert not (train_q & test_q), "Exact question leakage between train and test"
assert not (val_q & test_q), "Exact question leakage between validation and test"
assert not ({_plan(r) for r in check_train} & {_plan(r) for r in check_val}), "Plan leakage between train and validation"

print(f"Created {len(all_records)} expanded validated examples: {OUTPUT_PATH}")
print(f"Training: {len(check_train)} -> {SPLIT_DIR / 'train.jsonl'}")
print(f"Validation: {len(check_val)} -> {SPLIT_DIR / 'validation.jsonl'}")
print(f"Fixed test: {len(check_test)} -> {_FIXED_TEST_PATH} (preserved, not rewritten)")
print("Examples per operation in full expanded corpus:")
coverage = Counter(json.loads(r["messages"][-1]["content"])["operation_id"] for r in all_records)
for op_id in sorted(coverage):
    print(f"  {op_id}: {coverage[op_id]}")
print("Checks passed: exact-question separation across all splits; plan-group separation between train and validation.")
print("Note: fixed test questions are excluded, but test plans may be represented by different paraphrases in training.")
