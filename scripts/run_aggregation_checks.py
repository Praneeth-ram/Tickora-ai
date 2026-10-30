
from backend.services.dynamic_query_service import execute_query_plan

# Test 1: Sum overtime minutes for one employee.
overtime_plan = {
    "operation_id": "attendance.sum",
    "aggregate_field": "overtime_minutes",
    "filters": {
        "attendance_date": {
            "gte": "2026-10-01",
            "lte": "2026-10-23",
        }
    },
}

overtime_result = execute_query_plan(
    overtime_plan,
    employee_id=1,
)
print("\nOvertime result:")
print(overtime_result)


# Test 2: Count attendance records grouped by status.
group_plan = {
    "operation_id": "attendance.group_by",
    "group_by_field": "status",
    "aggregate_function": "count",
    "filters": {
        "attendance_date": {
            "gte": "2026-10-01",
            "lte": "2026-10-23",
        }
    },
}

group_result = execute_query_plan(
    group_plan,
    employee_id=1,
)
print("\nAttendance grouped by status:")
print(group_result)
