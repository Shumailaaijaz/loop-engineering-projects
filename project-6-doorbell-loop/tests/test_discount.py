import pytest

from app.discount import apply_tiered_discount


def test_no_discount_below_five():
    assert apply_tiered_discount(100.0, 1) == 100.0
    assert apply_tiered_discount(100.0, 4) == 100.0


def test_ten_percent_at_lower_boundary_five():
    # quantity == 5 must already receive the 10% tier.
    assert apply_tiered_discount(100.0, 5) == 90.0


def test_ten_percent_between_five_and_nine():
    assert apply_tiered_discount(100.0, 7) == 90.0
    assert apply_tiered_discount(100.0, 9) == 90.0


def test_twenty_percent_at_upper_boundary_ten():
    # quantity == 10 must already receive the 20% tier.
    assert apply_tiered_discount(100.0, 10) == 80.0


def test_twenty_percent_above_ten():
    assert apply_tiered_discount(100.0, 25) == 80.0


def test_zero_quantity_zero_total():
    assert apply_tiered_discount(0.0, 0) == 0.0


def test_negative_total_raises():
    with pytest.raises(ValueError):
        apply_tiered_discount(-10.0, 5)


def test_negative_quantity_raises():
    with pytest.raises(ValueError):
        apply_tiered_discount(10.0, -1)


def test_rounding_to_two_decimals():
    assert apply_tiered_discount(19.99, 5) == 17.99
