# Bug Report — `remove_duplicates()` does not preserve order

## Summary

`app/inventory.py::remove_duplicates()` is supposed to remove duplicate
cart items while preserving the order in which they were first added
(the result is used to render an order summary / receipt, where item
order matters to the customer).

The current implementation is:

```python
def remove_duplicates(items):
    return list(set(items))
```

`set()` does not preserve insertion order. The output order depends on
CPython's hash-table bucket layout, not on the order items were added.

## Location

`app/inventory.py`, function `remove_duplicates` (currently the last
function in the file).

## Reproduction

```bash
cd app
python3 -c "from inventory import remove_duplicates; print(remove_duplicates([103, 42, 103, 7, 42, 500]))"
```

Expected output (first-seen order, duplicates removed):

```
[103, 42, 7, 500]
```

Actual output (order not preserved — reproducible/deterministic for
this input on CPython, but is an artifact of hashing, not intent):

```
[42, 7, 500, 103]
```

## Why existing tests didn't catch this

`app/test_inventory.py::test_remove_duplicates_removes_all_dupes` only
asserts `sorted(remove_duplicates(...)) == [1, 2, 3]` — it checks that
duplicates are gone but never checks order, so it passes whether or not
order is preserved. This is a weak/incomplete regression test, which is
exactly why the bug shipped.

## Expected behavior / acceptance criteria

1. `remove_duplicates(items)` removes duplicate values.
2. `remove_duplicates(items)` preserves the order each distinct value
   was **first** seen in `items`.
3. No unrelated behavior of `inventory.py` changes.
4. The full existing test suite continues to pass.
5. A regression test exists that would fail on the original buggy
   implementation and passes on a correct fix (order-sensitive, not
   just a "no duplicates" check).

These criteria are encoded independently of the implementer in
`reviewer/oracle_tests/test_remove_duplicates_bug.py` — see
`reviewer/REVIEWER.md`.
