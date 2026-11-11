import pytest

from backend.exceptions import RateLimitedError
from backend.services import login_rate_limiter as module
from backend.services.login_rate_limiter import LoginRateLimiter


def test_blocks_after_max_failures():
    limiter = LoginRateLimiter(max_attempts=3, window_seconds=60)
    for _ in range(3):
        limiter.check("ip:1.2.3.4")
        limiter.record_failure("ip:1.2.3.4")
    with pytest.raises(RateLimitedError) as exc:
        limiter.check("ip:1.2.3.4")
    assert exc.value.details["retry_after_seconds"] >= 1


def test_other_keys_are_not_affected():
    limiter = LoginRateLimiter(max_attempts=2, window_seconds=60)
    limiter.record_failure("ip:1.1.1.1")
    limiter.record_failure("ip:1.1.1.1")
    limiter.check("ip:2.2.2.2")


def test_reset_clears_failures():
    limiter = LoginRateLimiter(max_attempts=2, window_seconds=60)
    limiter.record_failure("email:a@x.test")
    limiter.record_failure("email:a@x.test")
    limiter.reset("email:a@x.test")
    limiter.check("email:a@x.test")


def test_window_expires(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    limiter = LoginRateLimiter(max_attempts=2, window_seconds=60)
    limiter.record_failure("k")
    limiter.record_failure("k")
    with pytest.raises(RateLimitedError):
        limiter.check("k")
    clock[0] += 61
    limiter.check("k")