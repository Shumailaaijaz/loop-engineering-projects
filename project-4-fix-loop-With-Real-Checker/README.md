# Project 4 — Worktree + Skill + Maker-Checker

**Concept:** Real bug, isolated implementation, independent reviewer, PR only on PASS.

## Objective

Build a small but real maker-checker coding loop that:

- documents the fix procedure as a **skill**,
- fixes a real bug **only** inside an isolated **git worktree**,
- is judged by a **reviewer that the implementer cannot influence**,
- opens a PR **only** when the reviewer returns `PASS`,
- and can be shown rejecting a deliberately incorrect fix with `FAIL`
  and concrete reasons.

The core principle: **the reviewer is the gatekeeper. The implementer
never decides the work is complete.**

## The bug

See [`BUG_REPORT.md`](BUG_REPORT.md) for full detail. Summary:
`app/inventory.py::remove_duplicates()` used `list(set(items))`, which
removes duplicates but does **not** preserve the order items were first
added — order that matters because the result is used to render a
cart/receipt summary. The existing test for it
(`test_remove_duplicates_removes_all_dupes`) only checked
`sorted(...)`, so it passed regardless of order — a realistic example
of a weak test letting a real bug ship.

## Layout

| Path | Purpose |
|---|---|
| `app/inventory.py` | The small application module containing the bug. |
| `app/test_inventory.py` | Pre-existing (weak) test suite. |
| `BUG_REPORT.md` | Bug description, reproduction, acceptance criteria. |
| `skills/fix-bug/SKILL.md` | The documented fix procedure (maker-checker). |
| `reviewer/REVIEWER.md` | What the reviewer checks and how to run it. |
| `reviewer/oracle_tests/` | Independent regression test, owned by the reviewer, not the implementer. |
| `scripts/review_fix.py` | The reviewer/checker CLI. Prints `PASS` or `FAIL` + reasons. Exit code 0/1. |
| `scripts/demo_project4.sh` | Runs both the good-fix and bad-fix paths end to end. |
| `evidence/good-fix/`, `evidence/bad-fix/` | Captured diffs, test output, and reviewer verdicts. |

## Worktree / branch strategy

`main` holds the buggy baseline plus all of the skill/reviewer/demo
infrastructure. Every fix attempt happens on its own branch, checked
out into its own **git worktree** under `.worktrees/` (gitignored), so
`main`'s working tree is never touched by implementation work:

```bash
git worktree add .worktrees/good-fix -b project4/good-fix
git worktree add .worktrees/bad-fix  -b project4/bad-fix
```

## Roles

- **Implementer (Maker)** — works only inside a worktree. Reproduces
  the bug, adds/updates a regression test, makes the smallest correct
  fix, runs tests, hands off the diff + test output as evidence. Never
  gets to declare the fix correct.
- **Reviewer (Checker)** — `scripts/review_fix.py`. Independently:
  - runs its own **oracle test** (`reviewer/oracle_tests/`), which the
    implementer cannot see fail-safe or edit,
  - confirms that oracle test **fails on the pre-fix baseline** (proves
    it actually detects the bug) and **passes on the candidate**,
  - checks the diff is scoped to `app/` only,
  - runs the full existing test suite for regressions,
  - prints exactly `PASS` or `FAIL` with concrete `Reason:` lines.

## PASS criteria

All of the following, checked mechanically, not asserted:
1. Diff vs `main` only touches files under `app/`.
2. The independent oracle test fails against `main` (sanity check on the oracle itself).
3. The independent oracle test passes against the candidate branch.
4. The full `app/` test suite passes on the candidate branch.

## FAIL criteria

Any of:
- No changes were made.
- Files outside `app/` were changed (implementer touched the checker/skill/rules).
- The oracle test fails against the candidate (the bug is not actually fixed per the acceptance criteria).
- Any test in the existing suite fails on the candidate (regression).

## PR gate

```
IF reviewer prints PASS (exit code 0):
    a PR MAY be opened for that branch
ELSE:
    a PR MUST NOT be opened
```

Enforced procedurally in `scripts/demo_project4.sh` — the `gh pr
create` command is only printed/considered after a `PASS`; on `FAIL`
the script prints "PR gate: FAIL -> PR creation forbidden" and stops.

## Running the demo

```bash
cd project-4-fix-loop-With-Real-Checker

# one-time setup: pytest needs to be importable by whichever python
# runs review_fix.py. Either create a local .venv/ (auto-detected by
# review_fix.py) or point PYTEST_PYTHON at any interpreter with pytest:
python3 -m venv .venv && .venv/bin/pip install pytest
# or: export PYTEST_PYTHON=/path/to/python-with-pytest

./scripts/demo_project4.sh
```

Runs the reviewer against both `project4/good-fix` and
`project4/bad-fix`, showing the PASS/PR-allowed path and the
FAIL/PR-blocked path back to back.

Note: this repo's checkout lives on a Windows-mounted drive under WSL
(`/mnt/d`), where `python -m venv` + `pip install` can be extremely
slow (many small file writes). If that happens, create the venv
somewhere on the native Linux filesystem instead (e.g. `/tmp`) and
point `PYTEST_PYTHON` at its `bin/python`.

## Limitations

**Update:** `gh` (GitHub CLI) has since been installed and
authenticated (`gh auth login`, device flow, HTTPS). `project4/good-fix`
was pushed to `origin`, and the real PR was opened:

- **PR #1** — https://github.com/Shumailaaijaz/loop-engineering-projects/pull/1
- Base: `main` (repo default branch) · Head: `project4/good-fix`
- Opened only after the reviewer re-confirmed `PASS` on the pushed branch.
- `project4/bad-fix` was never pushed and has no PR.

Note: this repo's local `main` was ahead of `origin/main` by two
commits (the Project 4 baseline + evidence commits) at the time the PR
was opened, and per the task's safety rules `main` itself was not
pushed. Because of that, PR #1's diff is computed against the older
`origin/main` and so includes the whole `project-4-fix-loop-With-Real-Checker/`
addition, not just the isolated one-file fix — this is expected given
what was and wasn't pushed, not a review or scope failure of
`review_fix.py` itself (which correctly scoped `project4/good-fix`'s
diff against local `main` to `app/` only — see
`evidence/good-fix/02_diff.txt`).

Below is preserved as a record of the original state, before `gh` was
available: `gh` (GitHub CLI) was **not installed** in this
environment, so no PR could be created. The exact command that would
open it once authenticated was documented instead; the run was
honestly reported as blocked rather than faked.

## Evidence

Full raw output for every step lives in `evidence/good-fix/`,
`evidence/bad-fix/`, and `evidence/demo_run.txt` (a full run of
`scripts/demo_project4.sh` showing both paths back to back). Summary
below.

### Good Fix

**Bug reproduction (on `main`, before fix):**
```
$ cd app && python3 -c "from inventory import remove_duplicates; print(remove_duplicates([103, 42, 103, 7, 42, 500]))"
[42, 7, 500, 103]
Expected: [103, 42, 7, 500]
```

**Fix (`project4/good-fix`, diff vs `main`):**
```diff
-    return list(set(items))
+    seen = set()
+    result = []
+    for item in items:
+        if item not in seen:
+            seen.add(item)
+            result.append(item)
+    return result
```
Plus one added regression test, `test_remove_duplicates_preserves_first_seen_order`.

**Tests (candidate branch):** `5 passed` (`app/test_inventory.py`, includes the new regression test).

**Reviewer verdict:**
```
PASS
```
(Oracle test passes on the candidate; oracle sanity-check confirms it correctly fails on `main`; diff scoped to `app/` only; full suite green.)

**PR result:** Created. **PR #1** —
https://github.com/Shumailaaijaz/loop-engineering-projects/pull/1
(`project4/good-fix` → `main`, open, not merged). See the "Update" note
under [Limitations](#limitations) for how `gh` was set up and why the
PR diff is larger than this single-file fix.

### Bad Fix

**Deliberately incorrect change (`project4/bad-fix`, diff vs `main`):**
```diff
-    return list(set(items))
+    # Deduplicate deterministically instead of relying on set() iteration order.
+    return sorted(set(items))
```
Plus a weak, self-authored test (`test_remove_duplicates_is_deterministic`) that only checks the result is duplicate-free and repeatable — never that order is first-seen order. This is a realistic mistake: it "fixes" the visible symptom (nondeterminism) without meeting the actual acceptance criteria (order preservation), and the implementer's own tests all pass, which is exactly the trap the reviewer has to see through.

**Reviewer verdict:**
```
FAIL
Reason: Independent oracle regression test (reviewer/oracle_tests/test_remove_duplicates_bug.py) FAILED against the candidate implementation.
  test_remove_duplicates_preserves_first_seen_order: assert [7, 42, 103, 500] == [103, 42, 7, 500]
  test_remove_duplicates_preserves_order_with_no_duplicates: assert [1, 2, 3, 4, 5] == [5, 4, 3, 2, 1]
```
Rejected even though the implementer's own `app/` test suite passed 5/5 — the reviewer never trusted that suite as sufficient, per `reviewer/REVIEWER.md`. The checker was strict on the first attempt; no tightening was needed.

**PR result:** No PR command was run or shown. `scripts/demo_project4.sh` prints `PR gate: FAIL -> PR creation forbidden.` and stops — the gate makes it structurally impossible to reach the `gh pr create` step on a `FAIL`.
