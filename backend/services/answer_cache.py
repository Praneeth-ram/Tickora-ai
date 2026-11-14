import hashlib
import os
import threading
import time
from typing import Any, Protocol

DEFAULT_ANSWER_TTL_SECONDS = 300
MAX_ENTRIES = 1000

class CacheBackend(Protocol):
    def get(self, key: str) -> Any | None: ...
    def set(self, key: str, value: Any, ttl_seconds: int) -> None: ...
    def delete_prefix(self, prefix: str) -> None: ...

class MemoryCache:
    """Process-local cache with per-entry expiry. Lost on restart."""

    def __init__(self, max_entries: int = MAX_ENTRIES) -> None:
        self._data: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self._max_entries = max_entries

    def get(self, key: str) -> Any | None:
        now = time.monotonic()
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            expires_at, value = item
            if expires_at <= now:
                del self._data[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        with self._lock:
            if len(self._data) >= self._max_entries:
                self._evict_expired_locked()
            if len(self._data) >= self._max_entries:
                self._data.pop(next(iter(self._data)))
            self._data[key] = (time.monotonic() + ttl_seconds, value)

    def delete_prefix(self, prefix: str) -> None:
        with self._lock:
            for key in [k for k in self._data if k.startswith(prefix)]:
                del self._data[key]

    def _evict_expired_locked(self) -> None:
        now = time.monotonic()
        for key in [k for k, (exp, _) in self._data.items() if exp <= now]:
            del self._data[key]

def _backend() -> CacheBackend:
    # Only the memory backend exists today. Redis is added later behind the same interface.
    return _memory

_memory = MemoryCache()

def _digest(*parts: Any) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()

def plan_key(normalized_question: str, today_iso: str, fingerprint_text: str) -> str:
    """Plans are shared across users: no identity in the key or the value."""
    return "plan:" + _digest(normalized_question, today_iso, fingerprint_text)

def answer_key(employee_id: int, role: str, normalized_question: str, today_iso: str) -> str:
    """Answers are per employee and role. The employee ID is always part of the key."""
    return f"answer:{employee_id}:{role}:" + _digest(normalized_question, today_iso)

def answer_prefix(employee_id: int) -> str:
    return f"answer:{employee_id}:"

def get_plan(key: str) -> dict | None:
    value = _backend().get(key)
    return dict(value) if value is not None else None

def set_plan(key: str, plan: dict, ttl_seconds: int) -> None:
    _backend().set(key, dict(plan), ttl_seconds)

def get_answer(key: str) -> dict | None:
    value = _backend().get(key)
    return dict(value) if value is not None else None

def set_answer(key: str, result: dict, ttl_seconds: int | None = None) -> None:
    ttl = ttl_seconds or int(os.getenv("ANSWER_CACHE_TTL_SECONDS", DEFAULT_ANSWER_TTL_SECONDS))
    _backend().set(key, dict(result), ttl)

def clear_answers_for(employee_id: int) -> None:
    """Call on logout or password change so one user's cached answers are removed."""
    _backend().delete_prefix(answer_prefix(employee_id))