"""Per-account fixed-window rate limiter.

`check` has no awaits, so on a single asyncio loop it is atomic without a lock.
State is per process: run one worker for an exact limit (documented in README).
"""
import math
import time
from collections.abc import Callable, Hashable


class FixedWindowLimiter:
    def __init__(self, limit: int, window_seconds: float = 60.0, clock: Callable[[], float] = time.monotonic):
        if limit < 1 or window_seconds <= 0:
            raise ValueError("limit and window must be positive")
        self.limit, self.window, self._clock = limit, window_seconds, clock
        self._state: dict[Hashable, tuple[float, int]] = {}

    def check(self, key: Hashable) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds). retry_after is 0 when allowed."""
        now = self._clock()
        started, count = self._state.get(key, (now, 0))
        if now - started >= self.window:
            started, count = now, 0
        if count >= self.limit:
            return False, max(1, math.ceil(self.window - (now - started)))
        self._state[key] = (started, count + 1)
        if len(self._state) > 10_000:
            self._evict(now)
        return True, 0

    def _evict(self, now: float) -> None:
        self._state = {k: v for k, v in self._state.items() if now - v[0] < self.window}
