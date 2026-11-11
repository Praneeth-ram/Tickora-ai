"""The model runs in-process: health reports it, and chat degrades to 503 when it is not loaded."""
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import model_inference
from backend.services.llm_chat_service import ModelUnavailableError


def test_health_reports_model_status():
    with TestClient(app) as client:  # runs the lifespan startup
        body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["model_loaded"] is model_inference.is_loaded()


def test_generate_plan_without_model_raises_unavailable():
    saved = dict(model_inference._state)
    model_inference._state.update(model=None, tokenizer=None)
    try:
        with pytest.raises(ModelUnavailableError):
            model_inference.generate_plan("How many leave types are there?")
    finally:
        model_inference._state.update(saved)
