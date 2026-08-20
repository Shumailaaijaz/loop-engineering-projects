# Project 8: Root README Sync Loop

**Concept:** The Full 6-Part Loop on a Real Chore (Capstone)

A production-style unattended loop that keeps one real, boring fact
about this monorepo correct: the root `README.md`'s project index. It
uses all six Loop Engineering parts — Heartbeat, Worktree, Skill,
Maker-Checker, Connector, Spine — plus budget guards, observability,
failure recovery, safe stop conditions, tests, and an honest one-week
validation procedure.

## The chore

**What:** the repository root `README.md` should list every
`project-N-*` directory that exists. As of this project's own
inspection, it did not — it was a single line, `# loop-engineering-projects`,
even with 7 other project directories already present. New
`project-N-*` directories get added periodically (this one included);
each time, the index goes stale again.

**Why this chore, and not another:** three candidates were considered
during inspection (documentation freshness on the root index, a
repo-wide test-health sweep, a dependency audit). The dependency audit
had almost no surface (no `requirements.txt`/lockfiles in this repo).
The test-health sweep is purely read-only and doesn't exercise a real
Maker output. The README index chore is genuinely useful (verified
stale *right now*), deterministic to check, single-file in scope, and
low risk — exactly what "safe to run unattended for a week" requires.
It also folds in a test-health signal for free: the Checker runs the
full repository test sweep as a regression safety net on every run,
even though the change itself is docs-only.

## Architecture

```text
                     CRON (daily, 08:17 local time)
                              |
                              v
                 heartbeat/run_loop.sh   <- HEARTBEAT
        (picks interpreter, durable stdout log; all real guards
         live in loop.py so manual runs get identical safety)
                              |
                              v
                     scripts/loop.py :: run()
        lock (duplicate-exec) -> STOP file (circuit breaker)
              -> daily run budget                <- SPINE (scripts/spine.py)
                              |
                    [only if all guards clear]
                              v
                   scripts/loop.py :: _execute()
                              |
                 read root README.md (main, read-only)
                              |
                 already-open PR from a prior run? --yes--> NOOP, stop
                              |no
                    every project referenced? --yes--> NOOP, stop
                              |no (drift found)
                              v
        git worktree add .worktrees/<run-id> -b          <- WORKTREE
              project8/readme-sync-<run-id>
                              |
                              v
             scripts/maker.py :: apply(worktree)          <- MAKER
        (skills/readme-index/SKILL.md's procedure:
         append-only patch, README.md only)
                              |
                     commit inside worktree
                              |
                              v
       scripts/checker.py :: review(worktree, repo_root,   <- CHECKER
                              base_sha, head_sha)
        run from the ORIGINAL checkout, never from inside
        the candidate -- scope, no-deletions, content,
        links, budget, full repo test sweep
                              |
                    FAIL --> 1 bounded repair attempt --> still FAIL?
                              |                                |
                             PASS                    stop, no publish,
                              |                       record reason
                              v
          scripts/connector.py :: publish(...)               <- CONNECTOR
        git push + `gh pr create`, base=main, PASS only
                              |
                              v
       worktree always removed; ledger.jsonl + spine.json
       always updated; STOP written after 3 consecutive
       non-success runs
```

## The six parts

### 1. Heartbeat

- **Trigger:** `cron`, one line, installed via `crontab`. Chosen because
  it's this repo's own established scheduler (Projects 3 and 7 both use
  it) and no CI system (`.github/workflows`) exists here — cron is what
  actually runs unattended on this machine, not a hypothetical.
- **Frequency:** daily. Deliberately conservative per the spec's
  instruction not to start aggressive — a chore this small doesn't need
  more, and a human should be able to read one PR a day, not a stream.
- **Entrypoint:** `heartbeat/run_loop.sh`, invoked by cron; it exists
  only to pick a working interpreter and guarantee output lands in
  `state/cron_stdout.log` even if cron's own mail/logging is
  misconfigured. All actual duplicate-execution, circuit-breaker, and
  budget logic lives in `scripts/loop.py` itself, so a manual run
  (`python3 scripts/loop.py --trigger manual`) goes through the exact
  same guards as a cron-triggered one.
- **Duplicate-execution prevention:** `scripts/spine.py::acquire_lock()`
  — an exclusive lockfile at `state/loop.lock`. A second invocation
  while one is running exits immediately (exit 0, logged, no ledger
  entry — it did no work, so it isn't a "run").
- **Stale-run handling:** a lock older than 15 minutes (well past the
  120s runtime budget) is treated as abandoned and reclaimed rather
  than blocking forever.
- **Timeout behavior:** see Budget Guards.

### 2. Worktree

- `git worktree add .worktrees/<run-id> -b project8/readme-sync-<run-id> <base-sha>`,
  same convention as Projects 4 and 5.
- **Location:** `.worktrees/` inside `project-8-your-own-daily-loop/`
  (gitignored) — matching Project 4's convention, since this loop's
  own `Agent`/subprocess work doesn't hit the `opencode`-specific
  `/mnt/d` indexing bottleneck Project 5 documented.
- **Branch naming:** `project8/readme-sync-<UTC-timestamp>-<pid>` — unique
  per run, never reused.
- **Isolation rule:** `main`'s working tree is never edited directly.
  The Maker only ever writes inside the worktree. The Spine's own
  files (`state/*`) live in the main checkout but are local runtime
  data, not code the Maker touches, and are gitignored (see Spine).
- **Cleanup:** the worktree and its branch are removed at the end of
  *every* run (`_cleanup_worktree` in `loop.py`), success or failure —
  nothing is left lying around to go stale.
- **Dirty/stale worktree:** `git worktree prune` runs at the start of
  every run before creating a new one, so a leftover registration from
  a crashed prior run (directory gone, git metadata still pointing at
  it) doesn't block the next run — proven in
  `tests/test_loop.py::test_stale_worktree_registration_does_not_crash_a_fresh_run`.
- **Merge/rebase failure:** doesn't apply here by construction — the
  loop never merges. It opens a PR against `main` and stops; a human
  merges (or doesn't). The worktree is always created fresh from the
  current `main` HEAD, so there is nothing to rebase.

### 3. Skill

[`skills/readme-index/SKILL.md`](skills/readme-index/SKILL.md) — the
exact procedure, allowed/forbidden files, stop and failure conditions.
Deliberately narrow: one task (sync the root README's project index),
not "improve the project."

### 4. Maker

[`scripts/maker.py`](scripts/maker.py). **Deliberately a plain
deterministic script, not an LLM call** — same reasoning Project 7
landed on for `morning_brief.py`: the task is mechanical (list
directories, check a substring, insert lines), so a script does it for
**$0/month**, with no flakiness and no prompt-injection surface from
repository content. It:

- lists `project-N-*` directories at the repo root,
- checks which ones the current `README.md` doesn't already mention,
- for each, reads that project's *own* README's first heading as a
  one-line description,
- appends `- [name](name/README.md) — description` under a
  `## Projects` heading (creating it if absent) — **only ever
  appends**; every existing line is preserved byte-for-byte, in order.

*Optional extension, documented but not implemented*: a
`MAKER_CLI=claude` knob mirroring Project 5's swappable-Maker pattern,
for anyone who wants prose-drafted descriptions instead of the first
README heading. Not built for this capstone — it would add model
availability, cost, and non-determinism to something that doesn't need
any of the three, and "don't build for hypothetical future
requirements" argues against it here.

### 5. Checker

[`scripts/checker.py`](scripts/checker.py), always invoked with *this*
checkout's own copy — never the candidate worktree's — so a candidate
can't influence how it's graded (same rule as Projects 4/5). It
independently re-derives every answer rather than trusting the Maker's
report:

| Check | What it verifies |
|---|---|
| Scope | `git diff --name-only` between base and candidate is exactly `["README.md"]` |
| No deletions | every line in the base `README.md` is still present in the candidate |
| Content | re-runs `maker.missing_projects()` against the candidate; must be empty |
| Links | every new relative markdown link resolves to a real file in the candidate |
| Budget | files changed ≤ 1, lines changed ≤ 60 |
| Regression | the full repository test sweep (every `test_*.py` outside `.venv`/`.worktrees`/this project) still passes |

PASS only if every check passes. FAIL always comes with concrete,
specific reasons (`CheckResult.reasons`), never a bare "looks wrong" —
same standard as `reviewer/REVIEWER.md` in Project 4.

**A finding from testing this, not just designed in:** `loop.py` stages
only `README.md` before committing (`git add README.md`, never
`git add -A`), so a Maker write to any other file can never reach the
candidate commit the Checker evaluates — the scope check is real
defense-in-depth, but structurally unreachable through this
orchestrator today (see
`tests/test_loop.py::test_maker_writes_outside_readme_are_never_committed`).

**A second finding, from the actual dry run below:** the regression
sweep initially treated *any* repo-wide test failure as blocking —
which meant Project 4's oracle test (which correctly fails against
`main`, because Project 4's fix was only ever merged into a branch, see
that project's own README) would have permanently blocked this
unrelated, docs-only chore. Fixed: once `verify_scope` has already
confirmed the diff touches nothing but `README.md`, a failing test is
provably not this candidate's fault (the code it exercises is
byte-identical to `base_sha`) and is downgraded to a warning
(`CheckResult.warnings`) rather than a blocking reason. See
`tests/test_checker.py::test_review_warns_but_does_not_block_on_preexisting_unrelated_failure`
and `...test_review_fails_on_regression_when_scope_is_not_docs_only` for
both sides of that rule.

### 6. Connector

[`scripts/connector.py`](scripts/connector.py). Pushes the branch and
opens a real PR via `gh pr create`, base `main` — **only ever called
after `checker.review().passed` is `True`**; there is no code path in
`loop.py` that reaches `connector.publish()` on a FAIL. Mirrors
Project 4's PR #1 and Project 6's PR #2: opened, never auto-merged. A
human reviews and merges.

Before doing any of that, `connector.find_existing_open_pr()` checks
whether a previous run's PR is still open — if so, the run stops as a
`NOOP` rather than opening a second PR proposing the identical diff.

## Budget Guards

Defined in [`scripts/budget.py`](scripts/budget.py); enforced across
`spine.py`, `loop.py`, and `checker.py`. Any guard tripping means: stop
before the Connector, publish nothing, record why.

| Guard | Limit | Enforced by |
|---|---|---|
| Max runtime per iteration | 120s (deterministic Maker) | `signal.alarm()` wall-clock deadline in `loop.py::_execute` |
| Max files changed | 1 (`README.md`) | `checker.py::verify_budget` |
| Max lines changed | 60 | `checker.py::verify_budget` |
| Max repair attempts | 1 (bounded retry after a Checker FAIL) | `loop.py::_execute`'s attempt loop |
| Max consecutive failures | 3 -> writes `state/STOP` | `spine.py::record_run_finished` + `loop.py` |
| Max runs per day | 1 | `spine.py::runs_today` (independent of cron cadence — a guard, not just a schedule) |
| Max model/agent calls per run | 0 (default Maker is deterministic); 1 if the documented `MAKER_CLI=claude` extension were built | n/a in current code |

"Maximum tool/command calls" and "maximum iterations" aren't given
separate numeric caps: the task has exactly one iteration (no fan-out,
unlike Project 5), and every subprocess call the loop makes
(`git`, `gh`, `pytest`) already runs under its own timeout.

## Observability

Every real run (guards that short-circuit before `_execute` — the
duplicate-execution lock, the STOP file, the daily budget — are logged
but deliberately don't produce a ledger entry, since no run happened)
leaves:

- **`state/ledger.jsonl`** — one JSON object per run: `run_id`,
  `timestamp_utc`, `trigger`, `task`, `branch`, `worktree`,
  `maker_result`, `checker_passed`, `checker_reasons`, `tests`,
  `files_changed`, `lines_changed`, `repair_attempts`,
  `runtime_seconds`, `pr_url`, `final_status`,
  `circuit_breaker_tripped`. This answers "what did the loop do last
  night" without replaying anything.
- **`state/run.log`** — the same events, human-readable, one line per
  event (`spine.py::log`).
- **`state/spine.json`** — current machine state: `consecutive_failures`,
  `total_runs`, `last_run_utc`, `last_status`, `runs_today`.
- **`state/cron_stdout.log`** — raw stdout/stderr from the cron
  wrapper, as a last-resort trace if something breaks before Python
  even starts logging.

None of `state/*` is committed to git automatically — same convention
as `progress.md`/`brief.log` in Projects 3 and 7. Only the isolated
worktree branch is ever committed by the loop; `state/` is local
runtime data a human inspects directly or copies into `evidence/` at a
checkpoint of their choosing.

**To inspect what the loop did:**

```bash
cd project-8-your-own-daily-loop
tail -20 state/run.log
tail -5 state/ledger.jsonl | python3 -m json.tool --json-lines  # or: jq . state/ledger.jsonl
cat state/spine.json
```

## Failure Handling

| Failure | Handling |
|---|---|
| Maker exception (bad output) | caught by `_execute`'s top-level `except Exception`, recorded as `ERROR`, worktree cleaned up, nothing published |
| Checker FAIL | one bounded repair attempt (reset worktree, re-run Maker, re-check); still failing -> `FAIL`, stop, nothing published |
| Regression test failure | surfaces as a Checker FAIL reason (`"Regression: ..."`), same handling |
| Timeout / hang | `signal.alarm` fires, raises internally, recorded as `BUDGET_EXCEEDED`, worktree cleaned up in `finally` |
| `git push` failure (network) | `connector.publish` returns `published: False`; recorded as `CONNECTOR_FAILED`, not raised, not retried automatically |
| `gh pr create` failure | same as above — Checker had already passed, so this is reported distinctly (`checker_passed: true`, `final_status: CONNECTOR_FAILED`) so a human knows the *work* was fine and only *publishing* failed |
| Stale/dirty worktree registration | `git worktree prune` at the start of every run; a crashed run's leftover metadata never blocks the next one |
| Duplicate open PR | detected before any worktree is created; run stops as `NOOP`, no second PR |
| Duplicate execution | lockfile; second invocation is a no-op, not queued and not concurrent |
| Repeated failures | after 3 consecutive non-success runs, `state/STOP` is written; every subsequent run (cron or manual) is a no-op until a human deletes that file having investigated |
| Budget exhaustion | fails closed at whichever guard tripped; never publishes |
| Partial execution (push OK, PR failed) | recorded exactly as that — `CONNECTOR_FAILED` with the branch already on `origin`, visible via `git branch -r --list 'project8/readme-sync-*'` — nothing is silently lost |

No unsafe failure is ever silently swallowed: every path above ends in
either a ledger entry with `final_status` != `PUBLISHED`/`NOOP`, or a
`STOP` file, or both.

## Scheduler

Installed via `crontab`:

```
17 8 * * * /mnt/d/Loop-Engineering-Projects/project-8-your-own-daily-loop/heartbeat/run_loop.sh
```

Runs once daily at 08:17 (chosen off the hour, deliberately different
from Project 3/7's `0 7 * * *`, so the two loops' cron output doesn't
interleave in the same minute). This is the most conservative
unattended cadence that still produces a full week of evidence in a
week — the spec explicitly asks not to configure anything more
aggressive.

## Configuration

All tunables live in [`scripts/budget.py`](scripts/budget.py) (the
`Budget` dataclass) and as environment variables read by
`checker.py`/`connector.py`:

| Variable | Default | Purpose |
|---|---|---|
| `PYTEST_PYTHON` | project's own `.venv/bin/python`, else `~/.cache/loop-engineering-p5-pytest-venv/bin/python` (Project 5's bootstrapped interpreter, reused here), else `sys.executable` | interpreter used for the regression sweep |

## Manual execution

```bash
cd project-8-your-own-daily-loop

# one real run, identical guards to cron
python3 scripts/loop.py --trigger manual

# inspect what happened
tail -f state/run.log
cat state/ledger.jsonl | tail -1

# clear the circuit breaker after investigating a STOP
rm state/STOP
```

## Tests

```bash
cd project-8-your-own-daily-loop
PYTHONPATH=scripts python3 -m pytest -q tests/
# or, using the interpreter this repo already bootstrapped for pytest:
PYTHONPATH=scripts ~/.cache/loop-engineering-p5-pytest-venv/bin/python -m pytest -q tests/
```

28 tests, all passing at last run (see `state/ledger.jsonl`/dry-run
evidence below for the actual captured output). Every test runs
against a throwaway git repo built in `pytest`'s `tmp_path` — never
against this real monorepo. Coverage:

| # | Scenario | Test(s) |
|---|---|---|
| 1 | Normal successful run | `test_normal_successful_run` |
| 2 | Maker failure | `test_maker_failure_records_error_and_does_not_publish` |
| 3 | Checker rejection | `test_checker_rejection_blocks_publish_and_bounds_retries` |
| 4 | Test/regression failure | `test_regression_test_failure_blocks_publish` |
| 5 | Retry limit | `test_checker_rejection_blocks_publish_and_bounds_retries` (asserts exactly 1 repair attempt) |
| 6 | Budget exhaustion | `test_budget_exhaustion_blocks_publish` |
| 7 | Timeout | `test_timeout_trips_budget_exceeded` |
| 8 | Dirty/stale worktree | `test_stale_worktree_registration_does_not_crash_a_fresh_run` |
| 9 | Connector failure | `test_connector_failure_is_recorded_and_not_fatal_to_the_loop` (real `gh`, real local push, real PR-create failure — not mocked) |
| 10 | Duplicate execution prevention | `test_duplicate_execution_prevention` |
| 11 | Safe stop behavior | `test_safe_stop_behavior`, `test_circuit_breaker_trips_after_max_consecutive_failures` |

Plus `tests/test_maker.py` and `tests/test_checker.py` unit-test the
Maker and Checker in isolation (directory discovery, patch
construction, idempotency, scope/deletion/content/link/budget/
regression checks individually).

## Rollback / Recovery

- **A bad PR was opened:** it's not merged — close it on GitHub. Main
  is untouched (the loop never commits to it).
- **The loop tripped the circuit breaker:** read `state/run.log` and
  the last few `state/ledger.jsonl` entries for the failure reason,
  fix the underlying cause, then `rm state/STOP`. The next scheduled
  or manual run resumes normally — nothing about the failure streak or
  the STOP file blocks the *chore* itself once cleared.
- **A run is stuck / lock looks wedged:** the lock self-expires after
  15 minutes; to force it sooner, `rm state/loop.lock` (only after
  confirming via `ps` that no `loop.py` process is actually running).
- **Cron should stop entirely:** `crontab -e` and delete the
  `run_loop.sh` line (see Commands below).

## One-Week Validation Procedure

The loop is installed and running as of **2026-08-20**, daily at
08:17. Real elapsed time, not a simulation, is what the capstone asks
for — so this is the checklist for confirming it once seven days have
actually passed:

1. `crontab -l | grep run_loop.sh` — confirm the job is still
   installed (nobody removed it).
2. `wc -l state/ledger.jsonl` — expect roughly 7 entries (one per day;
   fewer only if `NOOP`s from an already-open PR suppressed a run, more
   only if a manual run was added).
3. For each ledger entry: read `final_status`. Expect mostly `NOOP`
   (nothing to do — the index only needs to change when a new
   `project-N-*` directory appears) or, if a real PR was opened,
   `PUBLISHED` followed by `NOOP`s once it's open (duplicate-PR guard).
4. `cat state/spine.json` — `consecutive_failures` should be `0` (or
   recently reset); if `state/STOP` exists, that's a real signal
   something needs a human, not a pass.
5. If any PR was opened: read the diff by hand (`gh pr diff <n>`),
   confirm it matches what Concept 15 below describes, then merge or
   close it as a human decision — the loop never merges for you.
6. Record the actual date range observed (e.g. "ran unattended
   2026-08-20 through 2026-08-27, N ledger entries, 0 unresolved
   STOPs") in this section, replacing the checklist with the real
   result.

**Status: NOT STARTED as elapsed real-world validation** — the loop is
built, tested, dry-run, and scheduled today (see below), but seven
actual days have not yet passed. This section will be updated with the
real observed evidence once they have; the code here does not claim
otherwise.

## Concept 15 — did understanding keep up with what the loop changed?

**What the loop can change:** at most one file, `README.md` at the
repo root, and only by appending bullet lines under a `## Projects`
heading — never editing or removing anything else. That's the entire
blast radius, verified independently by the Checker on every run
(scope + no-deletions checks), not just asserted by design.

**What was reviewed before enabling unattended operation:** every line
of `maker.py`, `checker.py`, `connector.py`, `loop.py`, and
`spine.py` was written and read in this session, plus a manual dry
run (below) was inspected end-to-end — the actual diff, the actual
Checker verdict, the actual PR — before scheduling cron.

**Is the rate of change manageable?** Yes, clearly — a docs-only,
single-file, append-only change, at most once a day, is far below what
a human can review in the time it takes to read one PR. This is
deliberately the opposite end of the spectrum from a loop that
refactors code: the chore was chosen in Phase 1 specifically because
its blast radius is small enough that daily unattended operation is
safe to reason about by inspection, not just by trusting the tests.

**Should the loop be slowed down?** No — at daily cadence, with a
budget of at most one PR touching at most one file, there is nothing
here that would outpace a human's ability to read and understand each
proposed change before merging it. If this chore's scope ever grew
(e.g., editing code instead of one docs file), that would be the
moment to revisit cadence, not before.

**Evidence supporting this:** the Checker's own verdict on every run
(`state/ledger.jsonl`), the Skill's explicit forbidden-files list, and
the fact that the Connector never merges — every published change
waits for a human to read it first, by construction, not by
convention.

## Files

```text
project-8-your-own-daily-loop/
├── README.md                    # this file
├── .gitignore                   # excludes .worktrees/, state/ runtime files
├── heartbeat/
│   └── run_loop.sh              # Heartbeat entrypoint (cron calls this)
├── skills/readme-index/
│   └── SKILL.md                 # the narrow, documented procedure
├── scripts/
│   ├── budget.py                # Budget guard constants
│   ├── spine.py                 # Spine: state, ledger, lock, STOP file
│   ├── maker.py                 # Maker: deterministic README patcher
│   ├── checker.py               # Checker: independent verification
│   ├── connector.py             # Connector: git push + gh pr create
│   └── loop.py                  # Orchestrator wiring all six parts
├── tests/
│   ├── conftest.py              # throwaway-git-repo fixtures
│   ├── test_maker.py
│   ├── test_checker.py
│   └── test_loop.py
├── state/                       # runtime data (gitignored): ledger, log, spine, lock, STOP
└── evidence/                    # dated, committed snapshots of real runs
```

## Commands

```bash
# Inspect
tail -20 project-8-your-own-daily-loop/state/run.log
tail -5 project-8-your-own-daily-loop/state/ledger.jsonl
cat project-8-your-own-daily-loop/state/spine.json
crontab -l | grep run_loop.sh

# Start (already installed; re-run only if removed)
( crontab -l 2>/dev/null; echo "17 8 * * * /mnt/d/Loop-Engineering-Projects/project-8-your-own-daily-loop/heartbeat/run_loop.sh" ) | crontab -

# Stop
crontab -l | grep -v 'project-8-your-own-daily-loop/heartbeat/run_loop.sh' | crontab -

# Run once, manually, with the same guards as cron
cd project-8-your-own-daily-loop && python3 scripts/loop.py --trigger manual

# Troubleshoot a tripped circuit breaker
cat project-8-your-own-daily-loop/state/STOP
rm project-8-your-own-daily-loop/state/STOP   # only after reading why

# Run the test suite
cd project-8-your-own-daily-loop && PYTHONPATH=scripts python3 -m pytest -q tests/
```
