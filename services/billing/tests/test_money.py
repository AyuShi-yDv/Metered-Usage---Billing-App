from app.money import overage_cents
def test_rounds_once_half_up():
    assert overage_cents(1, 500) == 1
    assert overage_cents(1, 499) == 0
    assert overage_cents(1001, 125) == 125
