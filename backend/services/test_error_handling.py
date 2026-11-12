"""Every API error uses the same JSON shape with a machine-readable code."""
from fastapi.testclient import TestClient

from backend.errors import (
    NotFoundError,
    ServiceUnavailableError,
    register_exception_handlers,
)
from backend.main import app

client = TestClient(app, raise_server_exceptions=False)


def _assert_error_shape(response, status_code, code):
    assert response.status_code == status_code
    body = response.json()
    assert body["detail"] == body["error"]["message"]
    assert body["error"]["code"] == code
    assert "details" in body["error"]


def test_missing_token_returns_json_401():
    response = client.get("/api/attendance/EMP001", params={"start_date": "2026-10-01", "end_date": "2026-10-31"})
    _assert_error_shape(response, 401, "unauthorized")


def test_invalid_request_body_returns_json_422():
    response = client.post("/api/auth/login", json={})
    _assert_error_shape(response, 422, "validation_failed")
    assert isinstance(response.json()["error"]["details"], list)


def test_unknown_route_returns_json_404():
    response = client.get("/api/does-not-exist")
    _assert_error_shape(response, 404, "not_found")


def test_app_error_subclasses_carry_their_status_and_code():
    mini = __import__("fastapi").FastAPI()
    register_exception_handlers(mini)

    @mini.get("/boom")
    def boom():
        raise NotFoundError("Leave request 42 was not found.", details={"id": 42})

    @mini.get("/down")
    def down():
        raise ServiceUnavailableError("Chat is currently disabled.")

    not_found = TestClient(mini).get("/boom")
    _assert_error_shape(not_found, 404, "not_found")
    assert not_found.json()["error"]["details"] == {"id": 42}

    unavailable = TestClient(mini).get("/down")
    _assert_error_shape(unavailable, 503, "service_unavailable")


def test_unexpected_exceptions_hide_internals():
    mini = __import__("fastapi").FastAPI()
    register_exception_handlers(mini)

    @mini.get("/crash")
    def crash():
        raise RuntimeError("secret database password in traceback")

    response = TestClient(mini, raise_server_exceptions=False).get("/crash")
    _assert_error_shape(response, 500, "internal_error")
    assert "secret" not in response.text
