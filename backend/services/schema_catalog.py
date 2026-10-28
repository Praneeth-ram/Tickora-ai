from functools import lru_cache
from typing import Any
from sqlalchemy import inspect

SENSITIVE_TABLE_TOKENS = {
    "credential", "password", "token", "secret",
    "face", "embedding", "salary",
    "payment", "deduction",
}

SENSITIVE_COLUMN_TOKENS = {
    "password", "token", "secret", "hash", "embedding",
}

def _is_sensitive_table(name: str) -> bool:
    name = name.lower()
    return any(token in name for token in SENSITIVE_TABLE_TOKENS)

def _is_sensitive_column(name: str) -> bool:
    name = name.lower()
    return any(token in name for token in SENSITIVE_COLUMN_TOKENS)

@lru_cache(maxsize=8)
def discover_schema(
    schema_name: str = "public",
    db_engine=None,
) -> dict[str, Any]:
    """Discover database metadata using trusted schema configuration."""
    if db_engine is None:
        from backend.db import engine as db_engine

    inspector = inspect(db_engine)
    catalog = {}

    for table_name in sorted(
        inspector.get_table_names(schema=schema_name)
    ):
        if _is_sensitive_table(table_name):
            continue

        columns = inspector.get_columns(
            table_name, schema=schema_name
        )

        safe_columns = [
            {
                "name": column["name"],
                "type": str(column["type"]),
                "nullable": bool(column.get("nullable", True)),
                "primary_key": False,
            }
            for column in columns
            if not _is_sensitive_column(column["name"])
        ]

        pk = inspector.get_pk_constraint(
            table_name, schema=schema_name
        )
        pk_columns = set(pk.get("constrained_columns") or [])

        for column in safe_columns:
            column["primary_key"] = column["name"] in pk_columns

        safe_names = {column["name"] for column in safe_columns}
        foreign_keys = []

        for fk in inspector.get_foreign_keys(
            table_name, schema=schema_name
        ):
            local_columns = fk.get("constrained_columns") or []
            referenced_columns = fk.get("referred_columns") or []
            referenced_table = fk.get("referred_table")

            if (
                referenced_table
                and not _is_sensitive_table(referenced_table)
                and all(name in safe_names for name in local_columns)
                and not any(
                    _is_sensitive_column(name)
                    for name in referenced_columns
                )
            ):
                foreign_keys.append({
                    "columns": local_columns,
                    "referred_schema": (
                        fk.get("referred_schema") or schema_name
                    ),
                    "referred_table": referenced_table,
                    "referred_columns": referenced_columns,
                })

        catalog[table_name] = {
            "schema": schema_name,
            "columns": safe_columns,
            "foreign_keys": foreign_keys,
        }

    return catalog

def clear_schema_catalog_cache() -> None:
    """Call after a trusted schema migration."""
    discover_schema.cache_clear()

def discover_schema_candidates(
    schema_name: str = "public",
) -> list[dict[str, Any]]:
    """List discovered tables for review, not automatic authorization."""
    catalog = discover_schema(schema_name)

    return [
        {
            "table": table_name,
            "columns": [
                column["name"] for column in metadata["columns"]
            ],
            "foreign_keys": metadata["foreign_keys"],
            "requires_policy_review": True,
        }
        for table_name, metadata in catalog.items()
    ]