"""Generate tests/fixtures/attendance_eval.json (56 cases).

Conventions (fixed here so scoring is consistent):
- today = 2026-11-18, employee_id = 1, organization_id = 1
- "last week"  = 2026-11-09 .. 2026-11-15  (Mon-Sun before this week)
- "this month" = 2026-11-01 .. 2026-11-18  (month-to-date)
- "last month" = 2026-10-01 .. 2026-10-31
- "late" means status == "late"
- relative dates: expected_raw has no date filter (the model may invent one;
  the correction step must fix it); expected_final has the resolved dates.
- sums over short ranges are corrected to attendance.list (design choice).
"""
import json
import sys
from pathlib import Path

REL = {
    "last week": ("2026-11-09", "2026-11-15"),
    "this month": ("2026-11-01", "2026-11-18"),
    "last month": ("2026-10-01", "2026-10-31"),
}
DATE = "attendance_date"
cases = []


def case(cid, group, question, op, filters=None, *, agg=None, gb=None,
         rel=None, final_op=None):
    filters = dict(filters or {})
    raw = {"operation_id": op, "filters": filters}
    if agg:
        raw["aggregate_field"] = agg
    if gb:
        raw["group_by_field"] = gb
        raw["aggregate_function"] = "count"

    # Out-of-scope: the planner should produce no operation, so there is no
    # corrected plan to compare.
    if op is None:
        cases.append({"id": cid, "group": group, "question": question,
                      "expected_raw": raw, "expected_final": None})
        return

    if rel:
        start, end = REL[rel]
        f = {k: v for k, v in filters.items() if k != DATE}
        f[DATE] = {"gte": start, "lte": end}
    else:
        f = dict(filters)

    # Sums over short ranges are corrected to list (design choice).
    final_op_value = final_op or op
    if op == "attendance.sum" and not final_op:
        final_op_value = "attendance.list"

    final = {"operation_id": final_op_value, "filters": f}
    if agg:
        final["aggregate_field"] = agg
    if gb:
        final["group_by_field"] = gb
        final["aggregate_function"] = "count"
    cases.append({"id": cid, "group": group, "question": question,
                  "expected_raw": raw, "expected_final": final})


def rng(s, e):
    return {DATE: {"gte": s, "lte": e}}


# --- absent / late / status counts, relative ---
case("ATT-001", "absent-last-week", "How many days was I absent last week?",
     "attendance.count", {"status": "absent"}, rel="last week")
case("ATT-002", "absent-last-week", "Number of absent days last week",
     "attendance.count", {"status": "absent"}, rel="last week")
case("ATT-003", "absent-last-week", "How many absences did I have last week?",
     "attendance.count", {"status": "absent"}, rel="last week")
case("ATT-004", "absent-last-week", "hw many days absnt last wek",
     "attendance.count", {"status": "absent"}, rel="last week")
case("ATT-005", "absent-last-week", "Was I absent on any day last week?",
     "attendance.count", {"status": "absent"}, rel="last week")

case("ATT-006", "late-count", "How many late days did I have last week?",
     "attendance.count", {"status": "late"}, rel="last week")
case("ATT-007", "late-count", "How many times was I late this month?",
     "attendance.count", {"status": "late"}, rel="this month")
case("ATT-008", "late-count", "how many times was i late last month",
     "attendance.count", {"status": "late"}, rel="last month")
case("ATT-009", "late-count", "Was I late on any day last week?",
     "attendance.count", {"status": "late"}, rel="last week")
case("ATT-010", "late-count", "late cnt last week",
     "attendance.count", {"status": "late"}, rel="last week")
case("ATT-011", "late-count", "How many late days in October?",
     "attendance.count", {"status": "late", **rng("2026-10-01", "2026-10-31")})

# --- present / half day / on leave counts, explicit months ---
case("ATT-012", "status-count", "How many days was I present in October?",
     "attendance.count", {"status": "present", **rng("2026-10-01", "2026-10-31")})
case("ATT-013", "status-count", "How many half days did I take in October?",
     "attendance.count", {"status": "half_day", **rng("2026-10-01", "2026-10-31")})
case("ATT-014", "status-count", "How many days was I on leave in October?",
     "attendance.count", {"status": "on_leave", **rng("2026-10-01", "2026-10-31")})
case("ATT-015", "status-count", "Days I was present in September?",
     "attendance.count", {"status": "present", **rng("2026-09-01", "2026-09-30")})
case("ATT-016", "status-count", "How many half days last month?",
     "attendance.count", {"status": "half_day"}, rel="last month")
case("ATT-017", "status-count", "How many days was I present last week?",
     "attendance.count", {"status": "present"}, rel="last week")

# --- hours and overtime sums ---
case("ATT-018", "hours-sum", "How many hours did I work this month?",
     "attendance.sum", agg="worked_minutes", rel="this month", final_op="attendance.list")
case("ATT-019", "hours-sum", "Total hours I worked last month",
     "attendance.sum", agg="worked_minutes", rel="last month", final_op="attendance.list")
case("ATT-020", "hours-sum", "How many hours did I work last week?",
     "attendance.sum", agg="worked_minutes", rel="last week", final_op="attendance.list")
case("ATT-021", "hours-sum", "hw mny hrs did i wrk this mnth",
     "attendance.sum", agg="worked_minutes", rel="this month", final_op="attendance.list")
case("ATT-022", "hours-sum", "How many hours did I work in October?",
     "attendance.sum", {**rng("2026-10-01", "2026-10-31")}, agg="worked_minutes")
case("ATT-023", "overtime-sum", "How much overtime did I do this month?",
     "attendance.sum", agg="overtime_minutes", rel="this month", final_op="attendance.list")
case("ATT-024", "overtime-sum", "overtime last week",
     "attendance.sum", agg="overtime_minutes", rel="last week", final_op="attendance.list")
case("ATT-025", "overtime-sum", "Total overtime in October",
     "attendance.sum", {**rng("2026-10-01", "2026-10-31")}, agg="overtime_minutes")

# --- status breakdowns (group_by status) ---
case("ATT-026", "status-breakdown", "Give me my attendance summary for 1 to 10 November",
     "attendance.group_by", rng("2026-11-01", "2026-11-10"), gb="status")
case("ATT-027", "status-breakdown", "attendance breakdown last week",
     "attendance.group_by", gb="status", rel="last week")
case("ATT-028", "status-breakdown", "attendance summary for October",
     "attendance.group_by", rng("2026-10-01", "2026-10-31"), gb="status")
case("ATT-029", "status-breakdown", "status breakdown this month",
     "attendance.group_by", gb="status", rel="this month")
case("ATT-030", "status-breakdown", "how many days per status in September",
     "attendance.group_by", rng("2026-09-01", "2026-09-30"), gb="status")
case("ATT-031", "status-breakdown", "attendance overview for last month",
     "attendance.group_by", gb="status", rel="last month")
case("ATT-032", "status-breakdown", "attndnce summry for octber",
     "attendance.group_by", rng("2026-10-01", "2026-10-31"), gb="status")

# --- clock-in / clock-out lookups on a single date ---
case("ATT-033", "clock-lookup", "When did I clock in on 3 November?",
     "attendance.list", {DATE: "2026-11-03"})
case("ATT-034", "clock-lookup", "What time did I clock in on 5 Nov?",
     "attendance.list", {DATE: "2026-11-05"})
case("ATT-035", "clock-lookup", "clock out time on 10 November",
     "attendance.list", {DATE: "2026-11-10"})
case("ATT-036", "clock-lookup", "check in on 12 Nov",
     "attendance.list", {DATE: "2026-11-12"})
case("ATT-037", "clock-lookup", "What time did I punch in on 2 October?",
     "attendance.list", {DATE: "2026-10-02"})
case("ATT-038", "clock-lookup", "When did I check out on 7 November?",
     "attendance.list", {DATE: "2026-11-07"})
case("ATT-039", "clock-lookup", "wen did i clok in on 4 nov",
     "attendance.list", {DATE: "2026-11-04"})

# --- record lists over ranges ---
case("ATT-040", "range-list", "Show my attendance records for 1 to 5 November",
     "attendance.list", rng("2026-11-01", "2026-11-05"))
case("ATT-041", "range-list", "attendance list for October",
     "attendance.list", rng("2026-10-01", "2026-10-31"))
case("ATT-042", "range-list", "list my late days in October",
     "attendance.list", {"status": "late", **rng("2026-10-01", "2026-10-31")})
case("ATT-043", "range-list", "show my absent days in September",
     "attendance.list", {"status": "absent", **rng("2026-09-01", "2026-09-30")})

# --- explicit-date counts with other wording ---
case("ATT-044", "explicit-count", "How many days in November was I absent?",
     "attendance.count", {"status": "absent", **rng("2026-11-01", "2026-11-30")})
case("ATT-045", "explicit-count", "absent days between 1 and 10 October",
     "attendance.count", {"status": "absent", **rng("2026-10-01", "2026-10-10")})
case("ATT-046", "explicit-count", "How many late days between 5 and 15 October?",
     "attendance.count", {"status": "late", **rng("2026-10-05", "2026-10-15")})
case("ATT-047", "explicit-count", "How many days was I absent on 6 October?",
     "attendance.count", {"status": "absent", DATE: "2026-10-06"})

# --- work location breakdowns ---
case("ATT-048", "location", "Where did I work in October?",
     "attendance.group_by", rng("2026-10-01", "2026-10-31"), gb="work_location")
case("ATT-049", "location", "work location breakdown this month",
     "attendance.group_by", gb="work_location", rel="this month")

# --- last-week summaries and mixed phrasing ---
case("ATT-050", "status-breakdown", "last week's attendance summary",
     "attendance.group_by", gb="status", rel="last week")
case("ATT-051", "status-count", "How many days did I miss last week?",
     "attendance.count", {"status": "absent"}, rel="last week")
case("ATT-052", "hours-sum", "Total worked minutes for last month",
     "attendance.sum", agg="worked_minutes", rel="last month", final_op="attendance.list")

# --- out of scope: the planner should not produce an attendance plan ---
case("ATT-053", "out-of-scope", "What's the weather today?", None)
case("ATT-054", "out-of-scope", "Write me a poem about working hours", None)
case("ATT-055", "out-of-scope", "Who is the CEO of my company?", None)
case("ATT-056", "out-of-scope", "What is the capital of India?", None)

out = {
    "meta": {"today": "2026-11-18", "employee_id": 1, "organization_id": 1,
             "late_convention": "status == late",
             "this_month": "month-to-date", "this_week": "not tested"},
    "cases": cases,
}
dest = Path(sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/attendance_eval.json")
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"wrote {len(cases)} cases to {dest}")