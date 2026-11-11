import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.services.operation_registry import (
    build_operation_registry,
    get_model_catalog,
)

registry = build_operation_registry()

print("Registered operations:")
for operation_id, definition in sorted(registry.items()):
    print(f"\n{operation_id}")
    print("  Table:", definition["table"])
    print("  Scope:", definition["scope"])
    print("  Fields:", definition["fields"])
    print("  Filters:", definition["filters"])

print("\nModel catalog:")
for operation in get_model_catalog(registry):
    print(operation)
