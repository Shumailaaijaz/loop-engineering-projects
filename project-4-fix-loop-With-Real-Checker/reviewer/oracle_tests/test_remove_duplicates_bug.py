"""Independent oracle regression test for BUG_REPORT.md.

Owned by the reviewer, NOT the implementer. The implementer (Maker) never
edits this file and its content is not trusted to come from the
implementer's own test additions. It encodes the bug report's acceptance
criteria and is run by scripts/review_fix.py against:

  1. The pre-fix baseline (app/inventory.py on `main`) — must FAIL,
     proving this oracle actually detects the reported bug.
  2. The candidate implementation in the implementer's worktree — must
     PASS for the reviewer to consider the fix correct.

This is what lets the reviewer avoid ever trusting the implementer's own
claim ("I fixed it") or the implementer's own tests as proof.
"""

from inventory import remove_duplicates


def test_remove_duplicates_preserves_first_seen_order():
    cart_codes = [103, 42, 103, 7, 42, 500]
    assert remove_duplicates(cart_codes) == [103, 42, 7, 500]


def test_remove_duplicates_actually_removes_duplicates():
    assert remove_duplicates([1, 1, 1]) == [1]


def test_remove_duplicates_preserves_order_with_no_duplicates():
    assert remove_duplicates([5, 4, 3, 2, 1]) == [5, 4, 3, 2, 1]
