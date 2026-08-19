# Reviewer Specification — project-6-doorbell-loop

This document is the checklist the automatic reviewer (Claude Code Routine) must
follow for every pull request opened or updated against this project's code.

The reviewer is invoked **automatically by a GitHub pull-request event** — it must
never be invoked manually, and it must never take the PR description, the author's
claims, or the author's own tests at face value.

## Scope

Only `project-6-doorbell-loop/**` is in scope. This repository hosts multiple
unrelated project folders on `main`; ignore changes outside this directory.

## Source of truth for correct behavior

`app/discount.py` implements a tiered quantity discount with this documented
contract (also stated in the module docstring and `README.md`):

```
quantity >= 10  -> 20% off the order total
quantity >= 5   -> 10% off the order total
quantity < 5    -> no discount
total  < 0      -> raise ValueError
quantity < 0    -> raise ValueError
result is rounded to 2 decimal places
```

Boundary quantities (**exactly 5** and **exactly 10**) belong to the **higher**
tier. This is the most common place for an off-by-one bug and must be checked
explicitly, with concrete numbers, not just "boundaries look handled."

## What the reviewer must do

1. **Read the diff directly.** Open the actual changed lines in `app/discount.py`
   (and any other changed source file). Do not infer correctness from the PR
   title, description, or commit message.
2. **Re-derive expected output by hand** for at least the boundary cases
   (quantity = 4, 5, 9, 10, 11) and compare against what the changed code would
   actually return. Trace the comparison operators (`>`, `>=`, `<`, `<=`)
   literally — do not assume they are correct because they "look reasonable."
3. **Do not trust the PR author's tests.** If tests were added or modified in the
   PR, independently check whether those tests would actually catch a
   boundary/off-by-one bug, or whether they were weakened/removed to hide one.
   A PR that passes its own (possibly tampered) tests is not sufficient evidence
   of correctness.
4. **Run the existing test suite** (`pytest tests/ -v` from
   `project-6-doorbell-loop/`) and report the actual result. Passing tests are
   necessary but never sufficient — pair this with your own independent trace.
5. **Check regression safety.** Confirm behavior for quantities well inside each
   tier (e.g. 1, 7, 25) is unchanged, and confirm the `ValueError` cases for
   negative `total`/`quantity` still raise.
6. **Look specifically for these classic bug shapes** in the diff:
   - off-by-one on a tier boundary (`>` instead of `>=`, or vice versa)
   - swapped or inverted comparison operators
   - wrong discount rate assigned to a tier
   - dropped or weakened input validation (missing `ValueError` checks)
   - incorrect rounding or return value

## Required output format

Post the review as a **GitHub pull-request review** (not just a comment) with:

- **Verdict**: `APPROVE` only if the implementation is actually correct, or
  `REQUEST_CHANGES` if a real correctness problem is found. Never approve solely
  because tests pass.
- **Explanation**: what you checked and why you reached this verdict, including
  the boundary values you traced by hand.
- **File/line reference** for any problem found (e.g. `app/discount.py:24`).
- **Recommended correction** — the exact fix (e.g. "change `quantity > 10` to
  `quantity >= 10`") if a bug is found.

A review that only says "LGTM, tests pass" is a failure of this specification,
even if no bug exists — the review must show the independent reasoning above.

## What the reviewer must NOT do

- Must not merge the PR.
- Must not approve based on the PR description or author claims alone.
- Must not skip tracing the boundary cases by hand.
