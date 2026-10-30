from typing import Any
from backend.services.schema_catalog import discover_schema

# Explicit allowlist: schema discovery alone never grants access.
ENTITY_POLICIES: dict[str, dict[str, Any]] = {
    "attendance_records": {
        "entity": "attendance",
        "scope": "employee_id",
        "list_fields": [
            "attendance_date",
            "clock_in",
            "clock_out",
            "status",
            "work_location",
            "worked_minutes",
            "overtime_minutes",
            "is_late",
        ],
        "filter_fields": [
            "attendance_date",
            "status",
            "work_location",
            "is_late",
        ],
        "date_field": "attendance_date",
        "count_allowed": True,
        "aggregate_fields": [
            "worked_minutes",
            "overtime_minutes",
        ],
        "group_by_fields": [
            "status",
            "work_location",
            "is_late",
        ],
    },
    "leave_requests": {
        "entity": "leave_request",
        "date_fields": ["start_date", "applied_at"],
        "scope": "employee_id",
        "list_fields": [
            "start_date",
            "end_date",
            "requested_days",
            "reason",
            "status",
            "applied_at",
        ],
        "filter_fields": [
            "start_date",
            "end_date",
            "status",
            "leave_type_id",
            "applied_at",
        ],
        "date_field": "start_date",
        "count_allowed": True,
    },
    "wfh_requests": {
        "entity": "wfh_request",
        "date_fields": ["start_date", "applied_at"],
        "scope": "employee_id",
        "list_fields": [
            "start_date",
            "end_date",
            "reason",
            "status",
            "applied_at",
        ],
        "filter_fields": [
            "start_date",
            "end_date",
            "status",
            "applied_at",
        ],
        "date_field": "start_date",
        "count_allowed": True,
    },
    "timesheets": {
        "entity": "timesheet",
        "date_fields": ["period_start", "submitted_at"],
        "scope": "employee_id",
        "list_fields": [
            "period_start",
            "period_end",
            "status",
            "submitted_at",
            "approved_at",
        ],
        "filter_fields": [
            "period_start",
            "period_end",
            "status",
            "submitted_at",
        ],
        "date_field": "period_start",
        "count_allowed": True,
    },
    "holidays": {
        "entity": "holiday",
        "scope": "organization_calendar",
        "list_fields": [
            "holiday_date",
            "name",
            "holiday_type",
        ],
        "filter_fields": [
            "holiday_date",
            "holiday_type",
        ],
        "date_field": "holiday_date",
        "count_allowed": True,
    },
    "leave_balances": {
        "entity": "leave_balance",
        "scope": "employee_id",
        "list_fields": [
            "year",
            "leave_type_id",
            "allocated_days",
            "used_days",
            "pending_days",
        ],
        "filter_fields": [
            "year",
            "leave_type_id",
        ],
        "date_field": None,
        "date_fields": [],
        "count_allowed": True,
        "aggregate_fields": [
            "allocated_days",
            "used_days",
            "pending_days",
        ],
        "group_by_fields": [
            "year",
            "leave_type_id",
        ],
    },
    "leave_types": {
        "entity": "leave_type",
        "scope": "global_read",
        "list_fields": ["id", "code", "name", "is_paid"],
        "filter_fields": ["code"],
        "date_field": None,
        "date_fields": [],
        "count_allowed": True,
    },
    "tasks": {
        "entity": "task",
        "scope": "employee_task",
        "identity_filters": {
            "assigned_to_employee_id": "employee_id",
            "managed_by_employee_id": "employee_id",
        },
        "list_fields": [
            "id",
            "title",
            "project_id",
            "task_date",
            "description",
            "start_time",
            "end_time",
            "status",
            "assigned_to_employee_id",
            "managed_by_employee_id",
            "performance_score",
        ],
        "filter_fields": [
            "task_date",
            "status",
            "project_id",
            "assigned_to_employee_id",
            "managed_by_employee_id",
        ],
        "date_field": "task_date",
        "count_allowed": True,
        "aggregate_fields": [
            "performance_score",
        ],
        "group_by_fields": [
            "status",
            "project_id",
            "assigned_to_employee_id",
            "managed_by_employee_id",
        ],
    },
}


def build_operation_registry(
    schema_name: str = "public",
) -> dict[str, dict[str, Any]]:
    catalog = discover_schema(schema_name)
    registry: dict[str, dict[str, Any]] = {}

    # Existing single-table operations.
    for table_name, policy in ENTITY_POLICIES.items():
        table = catalog.get(table_name)
        if table is None:
            continue

        available = {
            column["name"] for column in table["columns"]
        }
        scope = policy["scope"]

        if scope == "employee_id" and "employee_id" not in available:
            continue

        if scope == "employee_task" and not {
            "organization_id",
            "assigned_to_employee_id",
            "managed_by_employee_id",
        }.issubset(available):
            continue

        if scope == "organization_calendar":
            calendar_table = catalog.get("holiday_calendars")
            if calendar_table is None:
                continue
            calendar_columns = {
                column["name"] for column in calendar_table["columns"]
            }
            if not {"id", "organization_id"}.issubset(calendar_columns):
                continue
            if not {"calendar_id", "holiday_date"}.issubset(available):
                continue

        if scope not in {
            "employee_id",
            "employee_task",
            "global_read",
            "organization_calendar",
        }:
            continue

        fields = [
            field
            for field in policy["list_fields"]
            if field in available
        ]
        filters = [
            field
            for field in policy["filter_fields"]
            if field in available
        ]
        
        identity_filters = {
            field: context
            for field, context in policy.get("identity_filters", {}).items()
            if field in filters
        }

        if not fields:
            continue

        configured_date_field = policy.get("date_field")
        date_field = (
            configured_date_field
            if configured_date_field in available
            else None
        )

        date_fields = [
            field
            for field in policy.get("date_fields", [])
            if field in available
        ]

        if not date_fields and date_field:
            date_fields = [date_field]

        registry[f"{policy['entity']}.list"] = {
            "entity": policy["entity"],
            "table": table_name,
            "operation": "list",
            "scope": scope,
            "fields": fields,
            "filters": filters,
            "identity_filters": identity_filters,
            "date_field": date_field,
            "date_fields": date_fields,
            "aggregate_fields": [
                field
                for field in policy.get("aggregate_fields", [])
                if field in available
            ],
            "group_by_fields": [
                field
                for field in policy.get("group_by_fields", [])
                if field in available
            ],
        }

        if policy.get("count_allowed"):
            registry[f"{policy['entity']}.count"] = {
                "entity": policy["entity"],
                "table": table_name,
                "operation": "count",
                "scope": scope,
                "fields": [],
                "filters": filters,
                "identity_filters": identity_filters,
                "date_field": date_field,
                "date_fields": date_fields,
                "aggregate_fields": [],
                "group_by_fields": [],
            }

        aggregate_fields = [
            field
            for field in policy.get("aggregate_fields", [])
            if field in available
        ]
        group_by_fields = [
            field
            for field in policy.get("group_by_fields", [])
            if field in available
        ]

        if aggregate_fields:
            registry[f"{policy['entity']}.sum"] = {
                "entity": policy["entity"],
                "table": table_name,
                "operation": "sum",
                "scope": scope,
                "fields": [],
                "filters": filters,
                "identity_filters": identity_filters,
                "date_field": date_field,
                "aggregate_fields": aggregate_fields,
                "group_by_fields": group_by_fields,
            }

        if group_by_fields:
            registry[f"{policy['entity']}.group_by"] = {
                "entity": policy["entity"],
                "table": table_name,
                "operation": "group_by",
                "scope": scope,
                "fields": [],
                "filters": filters,
                "identity_filters": identity_filters,
                "date_field": date_field,
                "aggregate_fields": aggregate_fields,
                "group_by_fields": group_by_fields,
            }

    # Preserve the existing date-field normalization for single-table
    # operations. Payroll is registered after this loop because it does
    # not have a corresponding entry in ENTITY_POLICIES.
    for entry in registry.values():
        policy = ENTITY_POLICIES[entry["table"]]
        available = {
            column["name"]
            for column in catalog[entry["table"]]["columns"]
        }
        entry["date_fields"] = [
            field
            for field in policy.get(
                "date_fields", [policy["date_field"]]
            )
            if field in available
        ]

    # Payroll uses a dedicated three-table join in
    # dynamic_query_service.py, not the single-table query path.
    catalog_tables = {
        "employees",
        "payroll_summaries",
        "payroll_periods",
    }

    if catalog_tables.issubset(catalog):
        employees_columns = {
            column["name"]
            for column in catalog["employees"]["columns"]
        }
        summaries_columns = {
            column["name"]
            for column in catalog["payroll_summaries"]["columns"]
        }
        periods_columns = {
            column["name"]
            for column in catalog["payroll_periods"]["columns"]
        }

        required_employees = {
            "id",
            "organization_id",
        }
        required_summaries = {
            "employee_id",
            "payroll_period_id",
            "gross_amount",
            "deduction_amount",
            "net_amount",
            "currency",
        }
        required_periods = {
            "id",
            "organization_id",
            "period_start",
            "period_end",
        }

        if (
            required_employees.issubset(employees_columns)
            and required_summaries.issubset(summaries_columns)
            and required_periods.issubset(periods_columns)
        ):
            registry["payroll_summary.list"] = {
                "entity": "payroll_summary",
                "table": "payroll_summaries",
                "operation": "list",
                "scope": "employee_organization",
                "fields": [
                    "period_start",
                    "period_end",
                    "gross_amount",
                    "deduction_amount",
                    "net_amount",
                    "currency",
                ],
                "filters": [
                    "period_start",
                    "period_end",
                ],
                "date_field": "period_start",
                "date_fields": [
                    "period_start",
                    "period_end",
                ],
                "aggregate_fields": [],
                "group_by_fields": [],
            }

    return registry


def get_model_catalog(
    registry: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Expose approved capabilities, not unrestricted schema metadata."""
    return [
        {
            "operation_id": operation_id,
            "entity": definition["entity"],
            "operation": definition["operation"],
            "fields": definition["fields"],
            "filters": definition["filters"],
            "date_field": definition["date_field"],
            "aggregate_fields": definition.get("aggregate_fields", []),
            "group_by_fields": definition.get("group_by_fields", []),
        }
        for operation_id, definition in sorted(registry.items())
    ]
