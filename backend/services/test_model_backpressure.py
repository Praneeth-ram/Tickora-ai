import pytest
from backend.services import model_inference as mi
from backend.services.llm_chat_service import ModelUnavailableError

def test_busy_model_fails_fast(monkeypatch):
    monkeypatch.setattr(mi, "QUEUE_WAIT_SECONDS", 0.1)
    assert mi._generation_slots.acquire(timeout=1)
    try:
        with pytest.raises(ModelUnavailableError, match="busy"):
            with mi._generation_slot():
                pass
    finally:
        mi._generation_slots.release()

def test_slot_released_after_error():
    with pytest.raises(RuntimeError):
        with mi._generation_slot():
            raise RuntimeError("boom")
    assert mi._generation_slots.acquire(timeout=0.1)
    mi._generation_slots.release()