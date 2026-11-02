from backend.services.operation_registry import (
    build_operation_registry,
    get_model_catalog,
)
from backend.services.schema_catalog import discover_schema

registry = build_operation_registry()

print("\nTOTAL REGISTERED OPERATIONS:", len(registry))

print("\nREGISTERED ENTITIES:")
for operation_id, definition in sorted(registry.items()):
    print(f"\nOperation: {operation_id}")
    print(f"  Entity: {definition['entity']}")
    print(f"  Table: {definition['table']}")
    print(f"  Type: {definition['operation']}")
    print(f"  Scope: {definition['scope']}")
    print(f"  Fields: {definition['fields']}")
    print(f"  Filters: {definition['filters']}")
    print(f"  Aggregate fields: {definition.get('aggregate_fields', [])}")
    print(f"  Group by fields: {definition.get('group_by_fields', [])}")
    print(f"  Date fields: {definition.get('date_fields', [])}")

print("\nMODEL CATALOG:")
for item in get_model_catalog(registry):
    print(item)

