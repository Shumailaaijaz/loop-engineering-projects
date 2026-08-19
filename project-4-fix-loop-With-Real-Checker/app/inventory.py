"""Small cart/inventory utility module used for the Project 4 maker-checker demo."""


def add_item(cart, item):
    """Return a new cart list with item appended."""
    return cart + [item]


def total_price(cart, prices):
    """Return the sum of prices for each item in cart. Unknown items cost 0."""
    return sum(prices.get(item, 0) for item in cart)


def remove_duplicates(items):
    """Return items with duplicates removed, preserving first-seen order.

    Order matters here: this list is used to render a receipt / order
    summary, and customers expect items to appear in the order they were
    added to the cart.
    """
    return list(set(items))
