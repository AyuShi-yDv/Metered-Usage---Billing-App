def round_half_up(numerator: int, denominator: int = 1000) -> int:
    """Integer-only half-up rounding for non-negative money numerators."""
    if numerator < 0 or denominator <= 0: raise ValueError("positive values required")
    return (numerator + denominator // 2) // denominator

def overage_cents(overage_calls: int, cents_per_1000: int) -> int:
    return round_half_up(overage_calls * cents_per_1000)
