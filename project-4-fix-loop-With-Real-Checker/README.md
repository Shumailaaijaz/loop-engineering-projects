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
./scripts/demo_project4.sh
```

Runs the reviewer against both `project4/good-fix` and
`project4/bad-fix`, showing the PASS/PR-allowed path and the
FAIL/PR-blocked path back to back.

## Limitations

`gh` (GitHub CLI) is **not installed** in this environment, so no PR
was actually created. Evidence below documents the exact command that
would open it once authenticated; the run is honestly reported as
blocked rather than faked.

## Evidence

*(Filled in after the good-fix and bad-fix runs — see `evidence/good-fix/` and `evidence/bad-fix/` for full raw output.)*
