import json
from pathlib import Path

from backend.services.operation_registry import (
    build_operation_registry,
    get_model_catalog,
)

registry = build_operation_registry()
catalog = get_model_catalog(registry)

output = Path("data/model_catalog.json")
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(
    json.dumps(catalog, indent=2),
    encoding="utf-8",
)

print(f"Exported {len(catalog)} operations to {output}")
for operation in catalog:
    print(json.dumps(operation, ensure_ascii=False))
