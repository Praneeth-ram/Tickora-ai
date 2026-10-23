"""Offline tests for schema discovery filtering and operation registry shape."""
from backend.services.schema_catalog import (
    _is_sensitive_column,
    _is_sensitive_table,
)

def test_sensitive_tables_are_filtered():
    assert _is_sensitive_table("employee_credentials")
    assert _is_sensitive_table("refresh_token")
    assert _is_sensitive_table("user_face_embedding")
    assert not _is_sensitive_table("attendance_records")

def test_sensitive_columns_are_filtered():
    assert _is_sensitive_column("password_hash")
    assert _is_sensitive_column("refresh_token")
    assert _is_sensitive_column("center_embedding")
    assert not _is_sensitive_column("work_date")
