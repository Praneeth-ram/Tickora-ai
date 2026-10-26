
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
        "scope": "global_read",
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
}

def build_operation_registry(
    schema_name: str = "public",
) -> dict[str, dict[str, Any]]:
    catalog = discover_schema(schema_name)
    registry: dict[str, dict[str, Any]] = {}

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
        if scope not in {"employee_id", "global_read"}:
            continue

        fields = [
            field for field in policy["list_fields"]
            if field in available
        ]
        filters = [
            field for field in policy["filter_fields"]
            if field in available
        ]

        if not fields:
            continue

        configured_date_field = policy.get("date_field")
        date_field = (
            configured_date_field
            if configured_date_field in available
            else None
        )
 
        registry[f"{policy['entity']}.list"] = {
            "entity": policy["entity"],
            "table": table_name,
            "operation": "list",
            "scope": scope,
            "fields": fields,
            "filters": filters,
            "date_field": date_field,
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
                "date_field": date_field,
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
                "date_field": date_field,
                "aggregate_fields": aggregate_fields,
                "group_by_fields": group_by_fields,
            }
    
    for entry in registry.values():
        policy = ENTITY_POLICIES[entry["table"]]
        available = {column["name"] for column in catalog[entry["table"]]["columns"]}
        entry["date_fields"] = [
            field for field in policy.get("date_fields", [policy["date_field"]])
            if field in available
        ]

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
