"""Limits failed login attempts per client IP and per email address.

State is kept in memory, so limits apply per process. Run the backend
with a single worker, as the rest of the app already assumes.
"""
import threading
import time
from collections import defaultdict, deque
from backend.exceptions import RateLimitedError

MAX_FAILED_ATTEMPTS = 5
WINDOW_SECONDS = 60
_CLEANUP_THRESHOLD = 10_000

class LoginRateLimiter:
    def __init__(self, max_attempts: int, window_seconds: float) -> None:
        self._max_attempts = max_attempts
        self._window = window_seconds
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        attempts = self._failures.get(key)
        if attempts is None:
            return deque()
        while attempts and now - attempts[0] > self._window:
            attempts.popleft()
        if not attempts:
            self._failures.pop(key, None)
        return attempts

    def check(self, key: str) -> None:
        """Raise RateLimitedError if the key has too many recent failures."""
        now = time.monotonic()
        with self._lock:
            attempts = self._prune(key, now)
            if len(attempts) >= self._max_attempts:
                retry_after = max(1, int(self._window - (now - attempts[0])) + 1)
                raise RateLimitedError(
                    "Too many failed login attempts. Try again later.",
                    details={"retry_after_seconds": retry_after},
                )
            
    def hit(self, key: str) -> None:
        """Count one request; raise RateLimitedError when the window is full."""
        self.check(key)
        self.record_failure(key)

    def record_failure(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            self._prune(key, now)
            self._failures[key].append(now)
            if len(self._failures) > _CLEANUP_THRESHOLD:
                for stale_key in list(self._failures):
                    self._prune(stale_key, now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)

login_limiter = LoginRateLimiter(MAX_FAILED_ATTEMPTS, WINDOW_SECONDS)