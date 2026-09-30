import random
from fractions import Fraction

import pytest

from app.money import overage_cents, round_half_up


def test_rounds_once_half_up():
    assert overage_cents(1, 500) == 1      # 0.5 cents -> 1
    assert overage_cents(1, 499) == 0      # 0.499 cents -> 0
    assert overage_cents(1001, 125) == 125  # 125.125 -> 125
    assert overage_cents(3, 500) == 2      # 1.5 -> 2


def test_rounding_is_applied_to_the_total_not_per_event():
    per_event = sum(overage_cents(1, 400) for _ in range(1000))  # each 0.4c rounds to 0
    assert per_event == 0
    assert overage_cents(1000, 400) == 400  # the invoice-level figure is what is billed


def test_matches_exact_fraction_arithmetic_for_random_inputs():
    rng = random.Random(7)
    for _ in range(2000):
        calls, price = rng.randrange(0, 10_000_000), rng.randrange(0, 5000)
        exact = Fraction(calls * price, 1000)
        expected = int(exact + Fraction(1, 2)) if exact >= 0 else 0  # floor(x + 1/2) for x >= 0
        assert overage_cents(calls, price) == expected


def test_result_is_always_an_int():
    assert isinstance(overage_cents(10, 125), int)


@pytest.mark.parametrize("numerator,denominator", [(-1, 1000), (1, 0)])
def test_rejects_invalid_inputs(numerator, denominator):
    with pytest.raises(ValueError):
        round_half_up(numerator, denominator)
