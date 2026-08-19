# Reviewer (Checker)

The reviewer is the gatekeeper. It is a separate mechanism from the
implementer — a script (`scripts/review_fix.py`) plus a test file the
implementer does not control (`reviewer/oracle_tests/`). It never takes
the implementer's word for anything; it inspects the diff and runs its
own tests.

## What it evaluates

### Correctness
- Runs an **independent oracle test** (owned by the reviewer, not
  written or editable by the implementer) that encodes the bug
  report's acceptance criteria.
- Confirms the oracle test **fails against the pre-fix baseline**
  (`main`) — this proves the oracle actually detects the reported
  bug, not just a lucky guess.
- Confirms the oracle test **passes against the candidate
  implementation** in the worktree.
- Runs the implementer's own test file too, but only as *additional*
  evidence — it is never sufficient on its own, because an
  implementer's own test could be weak or written to pass trivially.

### Scope
- Computes `git diff <base>...<candidate branch>` and checks that only
  files under `app/` were changed.
- Rejects (FAIL) if the diff touches `reviewer/`, `skills/`,
  `scripts/`, or any file outside `app/` — the implementer must not be
  able to edit the checker or the rules.

### Regression safety
- Runs the **full** test suite in `app/` (all of `test_inventory.py`
  plus the oracle tests) inside the candidate worktree.
- Any failing test anywhere in that run is a FAIL, even if unrelated
  to the specific bug.

### Evidence
- The verdict is based only on command output the reviewer itself
  produced (pytest exit codes and captured output), never on prose
  claims.

## Verdict format

The script prints exactly one of:

```
PASS
```

or

```
FAIL
Reason: <specific, concrete reason>
Reason: <specific, concrete reason>
...
```

Vague approvals ("looks good", "probably fixed") are not valid output
and never appear — every FAIL reason names the specific check that
failed and, where applicable, the specific test name.

## Running it

```bash
python3 scripts/review_fix.py --worktree .worktrees/<fix-name> --base main
```

Exit code is `0` on `PASS`, `1` on `FAIL` — safe to use in a gate/CI
step.

## PR gate

```
IF review_fix.py exit code == 0 (PASS):
    a PR MAY be opened for the candidate branch
ELSE:
    a PR MUST NOT be opened
```

This is enforced procedurally: `scripts/demo_project4.sh` and the
skill both only proceed to the `gh pr create` step when the reviewer's
exit code is `0`. There is no code path that opens a PR on `FAIL`.
