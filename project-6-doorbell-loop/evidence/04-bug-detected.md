# Evidence 4 — Bug detected in the first automatic review

Review posted by GitHub App account `Shumailaaijaz` (the Claude GitHub App
acting on the routine owner's connected identity) at `2026-08-19T19:35:59Z`,
75 seconds after PR #2 was opened at `2026-08-19T19:34:44Z`, with **zero**
manual review requests in between. Full raw API payload:
[`03-automatic-review.json`](03-automatic-review.json).

## Key excerpt: the boundary trace that caught the off-by-one

| quantity | condition path | rate applied | contract says | match? |
|---|---|---|---|---|
| 4 | `4 > 10`→F, `4 >= 5`→F | 0% | 0% | ✅ |
| 5 | `5 > 10`→F, `5 >= 5`→T | 10% | 10% | ✅ |
| 9 | `9 > 10`→F, `9 >= 5`→T | 10% | 10% | ✅ |
| **10** | `10 > 10`→**F**, `10 >= 5`→T | **10%** | **20%** | ❌ |
| 11 | `11 > 10`→T | 20% | 20% | ✅ |

> At quantity = 10, the changed code returns `100.0 * 0.90 = 90.0`, but the
> documented contract ... requires `100.0 * 0.80 = 80.0`. This is a classic
> off-by-one: `>` was substituted for `>=` on the upper boundary.

## The reviewer also caught the disguised test tampering

> The PR also rewrites `test_twenty_percent_at_upper_boundary_ten` ... to
> assert `90.0` instead of the previously-correct `80.0` ... This doesn't
> validate the change — it just moves the test's expectation to match the
> bug, so the suite passes while the actual documented contract is violated.

This is exactly the failure mode `REVIEWER.md` requires the reviewer to
resist: trusting the PR author's own (silently weakened) tests instead of
independently re-deriving correctness from the documented contract.

## Verdict

`REQUEST CHANGES`, with the exact fix:

> `project-6-doorbell-loop/app/discount.py:24` — change `if quantity > 10:`
> back to `if quantity >= 10:`.
> `project-6-doorbell-loop/tests/test_discount.py` — revert
> `test_twenty_percent_at_upper_boundary_ten` to assert
> `apply_tiered_discount(100.0, 10) == 80.0`.
