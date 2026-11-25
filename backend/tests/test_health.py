
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from backend import main


@pytest.fixture(autouse=True)
def mock_application_startup(monkeypatch):
    """Prevent real database and model operations during test startup."""

    class FakeResult:
        def scalar_one(self):
            return 1

        def scalars(self):
            return self

        def all(self):
            return []

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, query):
            return FakeResult()

    # Prevent loading the real Qwen model.
    monkeypatch.setattr(
        main.model_inference,
        "load_model",
        lambda: None,
    )

    # Prevent connecting to the real PostgreSQL database during startup.
    monkeypatch.setattr(
        main.engine,
        "connect",
        lambda: FakeConnection(),
    )


def test_liveness_returns_200():
    with TestClient(main.app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_returns_200_when_dependencies_are_available(
    monkeypatch,
):
    monkeypatch.setattr(
        main.model_inference,
        "is_loaded",
        lambda: True,
    )

    with TestClient(main.app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"

    checks = response.json()["checks"]

    assert checks["database"] == "ok"
    assert checks["model"] == "ok"


def test_readiness_returns_503_when_database_is_down(
    monkeypatch,
):
    def failed_connection():
        raise SQLAlchemyError("Database unavailable")

    monkeypatch.setattr(
        main.engine,
        "connect",
        failed_connection,
    )

    monkeypatch.setattr(
        main.model_inference,
        "is_loaded",
        lambda: True,
    )

    with TestClient(main.app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503

    checks = response.json()["error"]["details"]["checks"]

    assert checks["database"] == "unavailable"
    assert checks["model"] == "ok"


def test_readiness_returns_503_when_model_is_not_loaded(
    monkeypatch,
):
    monkeypatch.setattr(
        main.model_inference,
        "is_loaded",
        lambda: False,
    )

    with TestClient(main.app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503

    checks = response.json()["error"]["details"]["checks"]

    assert checks["database"] == "ok"
    assert checks["model"] == "unavailable"
