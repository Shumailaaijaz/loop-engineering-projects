"""Tiered quantity discount calculator.

Documented behavior (see README.md for the full spec):

    quantity >= 10  -> 20% off the order total
    quantity >= 5   -> 10% off the order total
    quantity < 5    -> no discount

Boundary quantities (exactly 5 and exactly 10) belong to the higher tier.
"""


def apply_tiered_discount(total: float, quantity: int) -> float:
    """Return the order total after applying the tiered quantity discount.

    Raises:
        ValueError: if total is negative or quantity is negative.
    """
    if total < 0:
        raise ValueError("total must not be negative")
    if quantity < 0:
        raise ValueError("quantity must not be negative")

    if quantity >= 10:
        rate = 0.20
    elif quantity >= 5:
        rate = 0.10
    else:
        rate = 0.0

    discounted = total * (1 - rate)
    return round(discounted, 2)
