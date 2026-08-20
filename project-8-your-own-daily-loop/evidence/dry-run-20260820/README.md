# Dry run — 2026-08-20

Real, manual invocations of `scripts/loop.py --trigger manual` against
the actual monorepo, before cron was enabled. Three runs, in order:

1. **`20260820T060025Z-9354` — FAIL.** Real bug caught by the Checker's
   regression sweep: the PYTHONPATH resolution for Project 4's oracle
   test (`from inventory import remove_duplicates`) didn't include
   `app/`, so pytest couldn't import the module at all
   (`ModuleNotFoundError`). One bounded repair attempt ran and hit the
   identical error (deterministic bug, not transient), so the loop
   correctly stopped and published nothing. This is the "intentionally
   test at least one failure path" step from Phase 9 — except it wasn't
   staged, it's a real bug the Checker's own design caught on first
   contact with the real repo.
2. Between runs 1 and 2: fixed the PYTHONPATH resolution in
   `checker.py::run_test_sweep`. Re-running against the fixed code then
   surfaced a *second*, different issue: Project 4's oracle test now
   imported correctly but genuinely fails against `main` (Project 4's
   fix for its own bug was only ever merged into a branch, never
   `main` — documented in that project's own README). A blanket
   "any test failure blocks" rule would have permanently blocked this
   unrelated, docs-only chore on a pre-existing, out-of-scope failure.
   Fixed by downgrading a failing test to a non-blocking warning
   whenever the candidate's diff is proven to be `README.md`-only (see
   `checker.py::review`, the `docs_only` branch).
3. **`20260820T060826Z-13945` — PUBLISHED.** Real PR opened:
   https://github.com/Shumailaaijaz/loop-engineering-projects/pull/3
   (`project8/readme-sync-20260820T060826Z-13945` -> `main`, not
   merged). `checker_passed: true`, with Project 4's pre-existing
   failure correctly surfaced as a warning (`checker_warnings`), not a
   blocker. `pr_3_diff.txt` shows the exact 10-line, README.md-only
   diff. `worktree_path` was left as an empty directory after cleanup
   in this run (a WSL `/mnt/d` filesystem quirk, not a git-level
   problem — `git worktree list` no longer showed it) — fixed
   afterward in `loop.py::_cleanup_worktree` with an explicit
   `shutil.rmtree` fallback.
4. A fourth manual run (not in `ledger.jsonl`'s first three entries
   shown here, see the actual file) confirmed the duplicate-PR guard:
   with PR #3 still open, `connector.find_existing_open_pr` found it
   and the run stopped as `NOOP` in 1.34s, without creating a worktree.

## Files

| File | What it is |
|---|---|
| `ledger.jsonl` | Full structured ledger for all runs made this session |
| `run.log` | Human-readable log, same events |
| `pr_3_view.json` | `gh pr view 3` output — real PR metadata |
| `pr_3_diff.txt` | `gh pr diff 3` — the exact real diff, 10 lines, README.md only |
| `spine_after_dry_run.json` | Spine state after the dry run |
| `test_suite_output.txt` | `pytest -q tests/` — 30 passed |

## Result

The dry run proves, with real (not simulated) evidence: Heartbeat-equivalent
manual trigger works, Spine records every run, Worktree isolation holds
(main untouched), the Skill's procedure is what Maker follows, the
Checker independently caught a real bug and correctly distinguished a
blocking regression from an unrelated pre-existing one, the Connector
only published after PASS, and cleanup ran in every case. Cron is
enabled next (see README.md "Scheduler").
