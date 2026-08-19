---
name: fix-bug
description: Standard maker-checker procedure for fixing a real bug in this repo — isolated worktree, independent reviewer, PR only after PASS.
---

# Skill: Fix Bug (Maker-Checker)

This is the standard procedure for fixing any bug in this project. It
exists so that a fix is never accepted on the implementer's own say-so.

## Roles

- **Implementer (Maker)** — writes the fix. May propose that it is
  done. May **never** decide that it is *correct* or *complete*.
- **Reviewer (Checker)** — `scripts/review_fix.py`, described in
  `reviewer/REVIEWER.md`. The only party allowed to declare a fix
  correct. Uses an independent oracle test the implementer does not
  control.

**Never treat the implementer's own claim as proof that the fix is
correct.** "I fixed it", "the tests pass", "this looks right" are not
evidence. Only an independent reviewer inspecting the diff and running
tests it owns counts as evidence.

## Procedure

1. **Understand the bug.**
   Read the bug report (e.g. `BUG_REPORT.md`). Identify the exact
   expected behavior and acceptance criteria — not just "make some
   test pass."

2. **Reproduce the bug.**
   Run the reproduction steps in the bug report against the current
   (unfixed) code and confirm you observe the described wrong
   behavior. If you can't reproduce it, stop — you may be looking at
   the wrong bug.

3. **Read the relevant code.**
   Read the full function/module involved, not just the failing line.
   Understand why the current behavior is wrong, not only that it is.

4. **Add or identify a regression test.**
   A test that fails against the current buggy code and would pass
   against a correct fix. Prefer a test that checks the actual
   behavior described in the bug report (e.g. exact expected output),
   not a weakened check (e.g. "no duplicates" instead of "correct
   order") that could pass for the wrong reason.

5. **Create an isolated worktree/branch.**
   Never edit the fix directly on `main`.

   ```bash
   git worktree add .worktrees/<fix-name> -b project4/<fix-name>
   ```

6. **Implement the smallest correct fix.**
   Change only what is needed to satisfy the acceptance criteria.
   Do not refactor, rename, or "clean up" unrelated code in the same
   change.

7. **Run the relevant tests.**
   Run the regression test and the existing test suite for the
   changed module inside the worktree.

8. **Review the diff.**
   `git diff main...HEAD` inside the worktree. Confirm the change is
   scoped to the bug and nothing extraneous was touched.

9. **Give the reviewer the evidence.**
   Hand off: the worktree/branch name, the diff, and the test output.
   Do not summarize it as "done" — give the raw evidence.

10. **Only merge/open a PR after reviewer PASS.**
    Run `scripts/review_fix.py` against the worktree. Only if it
    prints `PASS` may a PR be opened (see the PR gate in
    `reviewer/REVIEWER.md`). On `FAIL`, read the concrete reasons,
    fix the implementation, and go back to step 6. Do not modify the
    reviewer's oracle test to force a pass.
