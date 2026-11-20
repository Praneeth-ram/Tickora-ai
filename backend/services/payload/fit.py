"""Keep each payload inside the token budget the responder can afford."""
from __future__ import annotations
import json
from typing import Any
from backend.services.payload.builders import PayloadError

MAX_PAYLOAD_TOKENS = 400


def compact_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)


def fit_payload(payload: dict[str, Any], tokenizer, max_tokens: int = MAX_PAYLOAD_TOKENS) -> dict[str, Any]:
    """Drop detail in order (rows first, then monthly breakdown) until it fits.

    Raises PayloadError if even the totals do not fit. The caller then uses the template.
    """
    def tokens(p: dict[str, Any]) -> int:
        return len(tokenizer.encode(compact_json(p)))

    if tokens(payload) <= max_tokens:
        return payload

    trimmed = dict(payload)
    for key in ("rows", "by_month"):
        if key in trimmed:
            trimmed.pop(key)
            trimmed["truncated"] = True
            if tokens(trimmed) <= max_tokens:
                return trimmed

    raise PayloadError("payload exceeds the token budget even after trimming")