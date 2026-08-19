from inventory import add_item, total_price, remove_duplicates


def test_add_item():
    assert add_item(["apple"], "banana") == ["apple", "banana"]


def test_total_price():
    prices = {"apple": 2, "banana": 1}
    assert total_price(["apple", "banana", "apple"], prices) == 5


def test_total_price_unknown_item_is_free():
    assert total_price(["mystery"], {}) == 0


def test_remove_duplicates_removes_all_dupes():
    assert sorted(remove_duplicates([1, 1, 2, 3, 3, 3])) == [1, 2, 3]


def test_remove_duplicates_preserves_first_seen_order():
    assert remove_duplicates([103, 42, 103, 7, 42, 500]) == [103, 42, 7, 500]
