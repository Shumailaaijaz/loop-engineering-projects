---
description: Draft fixes for the Project 4 bug in N parallel isolated worktrees, then grade each with the independent reviewer.
---

Codify the body of the Project 4 maker-checker fix loop. Do this as one
unattended run — do not stop to ask permission between steps, and do not
ask the user to describe the bug or the reviewer; both already exist.

Context you need is on disk, not in this prompt:
- The bug and acceptance criteria: `project-4-fix-loop-With-Real-Checker/BUG_REPORT.md`
- The fix procedure an implementer must follow: `project-4-fix-loop-With-Real-Checker/skills/fix-bug/SKILL.md`
- The independent reviewer, which you must not modify and whose exit
  code is the only thing that decides PASS/FAIL:
  `project-4-fix-loop-With-Real-Checker/scripts/review_fix.py`

Do exactly this:

1. **Fan out 3 candidates in parallel, isolated worktrees.** Candidates
   are named `candidate-1`, `candidate-2`, `candidate-3`. For each one,
   in the *same message* (so they run concurrently, not sequentially):
   - Create an isolated git worktree + branch off `main` for that
     candidate (e.g. `git worktree add .worktrees/<run-id>/<name> -b
     project5/<name>-<run-id> main`, run from
     `project-4-fix-loop-With-Real-Checker/`, mirroring how Project 4's
     own demo script created worktrees).
   - Dispatch an Agent (subagent_type: general-purpose) pinned to that
     worktree's `project-4-fix-loop-With-Real-Checker/` subdirectory.
     Tell it only what SKILL.md and BUG_REPORT.md already say: reproduce
     the bug, fix `app/inventory.py` so `remove_duplicates()` preserves
     first-seen order, add a real regression test (not a weakened one
     like `sorted()`), touch nothing outside `app/`, and not to declare
     the fix correct — an independent reviewer decides that.
   - Each candidate must not see the other candidates' work — that's
     what the separate worktrees are for.

2. **Wait for all three to finish** before moving on.

3. **Grade each candidate independently.** For each worktree, run
   `python3 project-4-fix-loop-With-Real-Checker/scripts/review_fix.py
   --worktree <candidate worktree path> --base main` from the *original*
   checkout (never from inside a candidate's own worktree — a candidate
   must not be able to influence how it's graded). Its exit code is the
   verdict: 0 = PASS, nonzero = FAIL. Do not re-judge the fix yourself;
   report exactly what the reviewer said, including its `Reason:` lines
   on FAIL.

4. **Report a verdict table** — one line per candidate: name, PASS/FAIL,
   worktree path. Do not open a PR for anything; that's a separate gate
   this command doesn't drive.

Run this whole thing with no memory of any previous run of this
command: pick a fresh run id, fresh worktree paths, fresh branch names.
Do not read any file this command wrote on a prior invocation.
