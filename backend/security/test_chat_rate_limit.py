import pytest
from backend.exceptions import RateLimitedError
from backend.services.login_rate_limiter import LoginRateLimiter


def test_thirty_first_chat_request_is_limited():
    limiter = LoginRateLimiter(max_attempts=30, window_seconds=60)
    for _ in range(30):
        limiter.hit("chat:1")
    with pytest.raises(RateLimitedError):
        limiter.hit("chat:1")


def test_limit_is_per_employee():
    limiter = LoginRateLimiter(max_attempts=30, window_seconds=60)
    for _ in range(30):
        limiter.hit("chat:1")
    limiter.hit("chat:2")  # a different employee is not affected