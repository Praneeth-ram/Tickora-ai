"""GPU-independent mocked inference tests for context-window integration."""
from contextlib import nullcontext
from datetime import date
from unittest.mock import MagicMock

import pytest
import torch

from backend.services import model_inference
from backend.services.context_window import ContextWindowExceededError


class _FakeTokenizer:
    eos_token_id = 0

    def encode(self, text: str, add_special_tokens: bool = False) -> list[int]:
        if not text:
            return []
        return list(range(1, len(text.split()) + 1))

    def apply_chat_template(
        self,
        messages: list[dict[str, str]],
        tokenize: bool = False,
        add_generation_prompt: bool = True,
    ) -> str:
        return "\n".join(f"{m['role']}: {m['content']}" for m in messages)

    def __call__(self, text: str, return_tensors: str = "pt", **kwargs):
        assert "truncation" not in kwargs, "Silent tokenizer truncation must not be used"
        ids = self.encode(text) or [1]
        tensor = torch.tensor([ids], dtype=torch.long)
        mask = torch.ones_like(tensor)
        result = MagicMock()
        result.input_ids = tensor
        result.__getitem__ = lambda _self, k: tensor if k == "input_ids" else mask
        result.to = lambda _device: result
        return result

    def decode(self, tokens, skip_special_tokens: bool = True) -> str:
        return '{"operation_id": "attendance.list", "filters": {}}'


def _setup_fake_inference(monkeypatch, system_prompt="sys"):
    fake_tok = _FakeTokenizer()
    fake_model = MagicMock()
    fake_model.get_input_embeddings.return_value.weight.device = torch.device("cpu")
    fake_model.disable_adapter.return_value = nullcontext()
    fake_model.generate.side_effect = lambda **kw: torch.cat(
        [kw["input_ids"], torch.tensor([[99]], dtype=torch.long)], dim=1
    )

    prefix_ids = fake_tok(f"system: {system_prompt}").input_ids
    monkeypatch.setitem(model_inference._state, "tokenizer", fake_tok)
    monkeypatch.setitem(model_inference._state, "model", fake_model)
    monkeypatch.setitem(model_inference._state, "system_prompt", system_prompt)
    monkeypatch.setitem(
        model_inference._state,
        "catalog",
        {"attendance.list": {"filters": ["attendance_date", "status"]}},
    )
    monkeypatch.setitem(
        model_inference._state,
        "prefix",
        {"date": date.today(), "ids": prefix_ids, "cache": {"k": "v"}},
    )
    return fake_model


def test_generate_plan_preserves_kv_cache_and_no_silent_truncation(monkeypatch):
    fake_model = _setup_fake_inference(monkeypatch, system_prompt="sys")
    plan = model_inference.generate_plan("Show my attendance")
    assert plan["operation_id"] == "attendance.list"
    call_kwargs = fake_model.generate.call_args.kwargs
    assert call_kwargs["past_key_values"] == {"k": "v"}


def test_generate_plan_raises_when_mandatory_content_exceeds_budget(monkeypatch):
    _setup_fake_inference(monkeypatch, system_prompt=" ".join(["sys"] * 9000))
    with pytest.raises(ContextWindowExceededError):
        model_inference.generate_plan("Show my attendance")


def test_generate_text_raises_when_mandatory_content_exceeds_budget(monkeypatch):
    _setup_fake_inference(monkeypatch, system_prompt="sys")
    huge_facts = " ".join(["fact"] * 9000)
    with pytest.raises(ContextWindowExceededError):
        model_inference.generate_text("sys", huge_facts, max_new_tokens=150)
