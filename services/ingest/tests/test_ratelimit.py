import pytest

from app.ratelimit import FixedWindowLimiter


class Clock:
    def __init__(self): self.now = 1000.0
    def __call__(self): return self.now


def test_blocks_after_limit_and_reports_retry_after():
    clock = Clock(); limiter = FixedWindowLimiter(3, 60, clock)
    assert [limiter.check("a")[0] for _ in range(3)] == [True, True, True]
    clock.now += 20
    allowed, retry_after = limiter.check("a")
    assert not allowed and retry_after == 40


def test_window_resets_and_accounts_are_independent():
    clock = Clock(); limiter = FixedWindowLimiter(1, 60, clock)
    assert limiter.check("a")[0] and not limiter.check("a")[0]
    assert limiter.check("b")[0]
    clock.now += 60
    assert limiter.check("a")[0]


def test_retry_after_is_at_least_one_second():
    clock = Clock(); limiter = FixedWindowLimiter(1, 60, clock)
    limiter.check("a"); clock.now += 59.9
    assert limiter.check("a") == (False, 1)


def test_rejects_invalid_configuration():
    with pytest.raises(ValueError):
        FixedWindowLimiter(0)
