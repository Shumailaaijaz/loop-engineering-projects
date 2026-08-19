# Project 5 — Codify the Body

**Concept:** the fix loop from Project 4 automated end to end — several
candidates, isolated checkouts, a verdict for each — driven by one
command, with proof that the command remembers nothing between runs.

## What "the body" is

Project 4 built the pieces: a real bug
([`BUG_REPORT.md`](../project-4-fix-loop-With-Real-Checker/BUG_REPORT.md)),
a documented fix procedure
([`skills/fix-bug/SKILL.md`](../project-4-fix-loop-With-Real-Checker/skills/fix-bug/SKILL.md)),
and an independent reviewer
([`scripts/review_fix.py`](../project-4-fix-loop-With-Real-Checker/scripts/review_fix.py))
that grades a candidate branch and exits 0 (PASS) or 1 (FAIL). Project 4
ran that reviewer against two branches a human had hand-written
(`good-fix`, `bad-fix`).

Project 5 doesn't touch any of that — it automates the step Project 4
still did by hand: **drafting the candidates.** One command now fans out
several independent implementer agents into isolated git worktrees,
lets each draft a fix with no visibility into the others' work, and
grades every one with the same unmodified reviewer. Nothing about the
bug, the procedure, or the checker changed; only the maker step got
codified.

**Design choice — what "three issues" means here:** three independent
parallel *attempts* at the one real bug from Project 4
(`candidate-1`, `candidate-2`, `candidate-3`), not three different bugs.
That's what "several candidates... isolated checkouts... a verdict for
each" describes, and it lets this project reuse Project 4's bug and
reviewer exactly as built instead of inventing new bugs just to have
three of them.

**Grading isolation, unchanged from Project 4:** the reviewer always
runs from the *original* checkout's copy of `review_fix.py` and
`reviewer/oracle_tests/`, never from inside a candidate's own worktree.
A candidate cannot influence how it's graded, even if its own copy of
`reviewer/` gets touched.

## The OpenCode approach — `scripts/opencode_fix_loop.sh`

One shell script. One command. No step-by-step prompting.

```bash
cd project-5-codify-the-body
./scripts/opencode_fix_loop.sh
```

What it does, mechanically:

1. **Fan-out (parallel, isolated).** A `for` loop over
   `candidate-1 candidate-2 candidate-3`; each iteration is
   backgrounded with `&`. Inside each: `git worktree add` creates a
   fresh branch + checkout off `main`, then a headless coding CLI
   (`$MAKER_CLI`, see below) drafts a fix inside that worktree only,
   following `BUG_REPORT.md` and `skills/fix-bug/SKILL.md`, with
   edit-only permissions and no view of the other two candidates. A
   single `wait` blocks until all three are done.
2. **Grade (sequential, independent).** For each candidate,
   `python3 review_fix.py --worktree <path> --base main` runs. **Its
   exit code is the checker** — 0 means PASS, nonzero means FAIL. There
   is no separate LLM-as-judge step; the script's own pass/fail table
   is read straight off `$?`.
3. **Report.** A verdict table, plus full logs and every reviewer
   transcript under `evidence/opencode-run-<run-id>/`.

### Real bugs this surfaced while building it (and how they were fixed)

Building this against real headless CLIs, not a mock, found three
genuine engineering problems before it worked end to end:

1. **Shared state under real parallelism.** `opencode` keeps its
   session state in one sqlite db under `$XDG_DATA_HOME/opencode`
   (default `~/.local/share/opencode/opencode.db`). Three concurrent
   `opencode run` processes hitting that one file threw
   `database is locked` and aborted instantly. Fix: each candidate gets
   its own `XDG_DATA_HOME` (`.opencode-data/` inside its worktree), so
   each has its own db and the fan-out is genuinely parallel instead of
   silently serialized-and-broken.
2. **The harness's own scaffolding leaking into the diff.** The scoped
   permission profile (`config/opencode.jsonc`) has to be copied into
   each candidate's project directory for `opencode` to pick it up —
   but if it's still sitting there when the script commits, the
   reviewer correctly flags it as a change outside `app/` and fails the
   candidate for something it didn't do. Fix: delete it after the maker
   step, and commit `app/` explicitly rather than `git add -A`.
3. **Google's free-tier quota, not this script, killed `opencode` as the
   live backend.** Iterating on (1) and (2) meant a lot of real headless
   invocations against the only provider configured for `opencode` in
   this environment (`google/gemini-2.5-flash` via `$GOOGLE_API_KEY`).
   That burned through the key's free-tier daily quota
   (`AI_APICallError: Quota exceeded ... generate_content_free_tier_requests,
   limit: 20`), and it stayed exhausted across models
   (`gemini-2.5-flash`, `gemini-3-flash-preview`, `gemini-2.5-flash-lite`)
   and after multi-minute cooldowns — a daily cap, not a per-minute one.
   The orchestration logic (isolate, fan out, grade by exit code) is
   identical either way, so the maker CLI became a swappable knob
   (`$MAKER_CLI`) instead of hard-coded to `opencode`, defaulting to
   `claude -p --permission-mode acceptEdits` so the two required proof
   runs (below) could actually execute. `MAKER_CLI=opencode` still
   exercises the exact code path that was validated (including fixes 1
   and 2) in isolated smoke tests before the quota ran out — set it once
   quota is available again.

None of these are special-case hacks bolted on after the fact — all
three are exactly the kind of thing an independent reviewer, and
honest evidence-keeping, are *for*. The second one in particular is a
small demonstration that the reviewer doesn't trust the harness driving
it any more than it trusts the implementer.

### Runtime knobs

| Env var | Default | Purpose |
|---|---|---|
| `MAKER_CLI` | `claude` | which headless CLI drafts each candidate: `claude` (`claude -p --permission-mode acceptEdits`) or `opencode` (`opencode run --model $MAKER_MODEL`) |
| `MAKER_MODEL` | `google/gemini-2.5-flash` | model each candidate agent uses, when `MAKER_CLI=opencode` |
| `MAKER_TIMEOUT` | `180` (seconds) | hard cap per candidate; real work reliably finishes well under this but the maker CLI doesn't always exit its own process promptly afterward, so the cap is generous, not tight |
| `WORKTREE_BASE` | `~/.cache/loop-engineering-p5-worktrees` | where candidate checkouts live — deliberately *not* under this repo's own `/mnt/d` mount, whose WSL 9p I/O is slow enough that indexing a 44-file checkout there ate an entire timeout with zero tool calls issued, in testing |
| `PYTEST_PYTHON` | auto-bootstrapped venv at `~/.cache/loop-engineering-p5-pytest-venv` | interpreter `review_fix.py` uses to run pytest |

## The Claude Code approach — dynamic workflows

The exercise's instruction for this half is to describe the job in
plain language to Claude Code — *"use a workflow to draft fixes for
these three issues in parallel worktrees, and have a reviewer grade
each one"* — and let the runtime write and run the orchestration
itself, then save the finished run from the `/workflows` view as a
reusable `/command`.

The literal `/workflows` flow (an interactive terminal session, a live
`/workflows` view, saving a finished run with a keystroke) needs an
interactive TTY this environment's tool-calling session doesn't have
direct control of. What's here instead is a hand-authored analogue,
[`.claude/commands/fix-loop-workflow.md`](.claude/commands/fix-loop-workflow.md)
— a standard Claude Code project slash command encoding the same body
in plain language (fan out 3 candidates into isolated worktrees, wait,
grade each with `review_fix.py` from the original checkout, report a
verdict table, read no state left behind by any previous invocation) —
and it **did** get driven end to end, for real, once the session
picked the command file up:

- **The mechanism, confirmed against current docs
  ([code.claude.com/docs/en/workflows](https://code.claude.com/docs/en/workflows)):**
  dynamic workflows are triggered by natural language in an interactive
  session (or the literal keyword `ultracode`); Claude Code writes an
  actual JavaScript orchestration script using `agent()`/`pipeline()`
  primitives to fan out up to 16 concurrent subagents, runs it in the
  background while the chat stays responsive, and — this is the part
  that matters for the second half of this project — **if you exit
  Claude Code while a workflow is running, the next session starts
  fresh; a workflow does not remember a prior run across sessions.**
  From the `/workflows` view, pressing `s` on a finished run saves it
  to `.claude/workflows/` (project) or `~/.claude/workflows/`
  (personal) as a `/<name>` command. The feature is explicitly labeled
  a research preview — behavior, caps, and resume semantics are
  documented as subject to change.
- **What actually ran:** once `.claude/commands/fix-loop-workflow.md`
  existed on disk, it registered as a real invokable command in this
  Claude Code session (confirmed by it appearing in the session's own
  skill listing) — the closest thing available here to "save a workflow
  and have it show up as a `/command`." Invoking it dispatched three
  real `Agent` subagents in parallel, each pinned to its own isolated
  git worktree/branch off `main`
  (`project5/candidate-{1,2,3}-20260819T182715Z-live`, now under
  `.worktrees/20260819T182715Z-live/`), each reading only
  `BUG_REPORT.md` and `skills/fix-bug/SKILL.md`, with no visibility
  into the other two. All three finished independently, and all three
  were graded by the unmodified `review_fix.py` from the original
  checkout:

  | Candidate | Verdict |
  |---|---|
  | candidate-1 | PASS |
  | candidate-2 | PASS |
  | candidate-3 | PASS |

  Evidence: `evidence/dynamic-workflow-run-20260819T182715Z-live/`.
  This is the real thing, not a simulation of it: one plain-language
  invocation, several candidates, isolated checkouts, an independent
  verdict for each, no step-by-step prompting after the command fired —
  it's just backed by a hand-authored `.claude/commands/` file instead
  of a `.claude/workflows/*.js` file the research-preview `/workflows`
  UI would have written.

## Proving the interlude's warning: the workflow remembers nothing

`./scripts/opencode_fix_loop.sh` was run twice, unmodified, no state
carried between invocations on purpose:

| Run | Run ID | Verdicts | Evidence |
|---|---|---|---|
| 1 | `20260819T135320Z-41064` | candidate-1 PASS, candidate-2 PASS, candidate-3 PASS | `evidence/opencode-run-20260819T135320Z-41064/` |
| 2 | `20260819T135517Z-41471` | candidate-1 PASS, candidate-2 PASS, candidate-3 PASS | `evidence/opencode-run-20260819T135517Z-41471/` |

(Both real, end-to-end runs — six headless `claude -p` invocations
total, six git worktrees, six independent `review_fix.py` gradings.
Earlier runs made while chasing the bugs above — including the ones
that failed outright against `opencode` before its quota was known to
be the cause — were deleted rather than kept as "evidence"; the two
kept here are the two that ran clean, back to back, once the harness
itself was debugged.)

What makes this a real test of statelessness, not just "it ran twice":

- Every run picks its own `RUN_ID` (`date -u ... -$$`) and derives every
  branch name, worktree path, and evidence directory from it — run 1's
  are `project5/candidate-1-20260819T135320Z-41064` etc., run 2's are
  `project5/candidate-1-20260819T135517Z-41471` etc. Run 2 never reads
  a file run 1 wrote.
- The three candidate agents in run 2 have no memory of what
  candidate-1/2/3 tried in run 1 — each is a brand-new headless process
  starting from `main`, in its own worktree, with no session or state
  directory shared with the previous run. If run 1's candidates had all
  failed for the same reason, run 2's candidates would fail (or pass)
  independently, for their own reasons — the script never tells them
  what happened last time, because it doesn't keep anything to tell.
- **The check that actually rules out a hidden shortcut:** all six
  candidates across both runs produced byte-identical `app/inventory.py`
  and `app/test_inventory.py` diffs. That is *not* evidence of shared
  state — it's the opposite. Nothing in the pipeline lets one candidate
  see another's answer, in the same run or across runs; six processes
  independently converging on the same fix is what you'd expect when
  six independent readings of the same bug report point to the same
  obvious, idiomatic Python pattern (`seen = set(); result = []; ...`).
  If run 2 had been secretly reading run 1's output, this would look
  exactly the same on the surface — which is why the real proof is
  structural (below), not "the answers matched."
- Nothing in the repo persists a "last run" pointer, a success/failure
  history, or a retry count. Delete the whole `$WORKTREE_BASE` directory
  and every `evidence/opencode-run-*/` directory and the *next*
  invocation of `./scripts/opencode_fix_loop.sh` behaves identically —
  because it already doesn't look at either. (Grep the script for
  `RUN_ID`: every path it touches is namespaced by it, and it's the
  only thing computed from *this* invocation's clock and PID — nothing
  is computed from, or read out of, anything on disk from before the
  script started.)

This is the interlude's point made concrete: what was just built is an
**engine** — something that, given a start signal, runs a fixed
procedure to completion and stops, carrying nothing forward. It is not
yet a **loop**.

## What it would take to become a loop

Two things, named, not built:

1. **A heartbeat** — something that fires `opencode_fix_loop.sh` (or
   `/fix-loop-workflow`) on its own, instead of a person typing the
   command. A cron entry, a scheduled wakeup, a file-watch, a webhook —
   any trigger that turns "run once when asked" into "run again without
   being asked."
2. **A progress file** — something every firing writes to and the next
   firing reads *before* acting, so run *N+1* knows what run *N*
   already tried, passed, or failed, instead of starting from a blank
   slate every time (which is exactly what was just proven above).
   Without it, a heartbeat alone just re-runs the same stateless engine
   on a timer — three fresh candidates, no memory, forever. The
   progress file is what would let the loop notice "candidate-2 passed
   last time, stop trying" or "all three failed twice in a row on the
   same reviewer reason, escalate" instead of repeating itself blindly.

Naming these two — and confirming their absence is exactly why two runs
of the same script above look statistically independent rather than
building on each other — is the deliverable for this half of the
exercise, not building them.

## Layout

| Path | Purpose |
|---|---|
| `scripts/opencode_fix_loop.sh` | The whole body: fan-out, isolate, draft, grade. One command. |
| `config/opencode.jsonc` | Scoped, edit-only permission profile handed to each candidate maker. |
| `.claude/commands/fix-loop-workflow.md` | The Claude Code slash-command analogue of the same body — the one that actually ran, see above. |
| `evidence/opencode-run-<run-id>/` | Per-candidate logs, diffs, and reviewer verdicts for each `opencode_fix_loop.sh` run. |
| `evidence/dynamic-workflow-run-<run-id>/` | Reviewer verdicts for the live `/fix-loop-workflow` run. |
| `$WORKTREE_BASE/<run-id>/` (default `~/.cache/loop-engineering-p5-worktrees/`) | `opencode_fix_loop.sh`'s candidate checkouts — outside the repo on purpose (see Runtime knobs: `opencode`'s file-watcher indexing a checkout on `/mnt/d`'s slow WSL 9p mount ate an entire timeout in testing). |
| `.worktrees/<run-id>/` (gitignored, inside the repo) | `/fix-loop-workflow`'s candidate checkouts — kept inside the project, matching Project 4's own convention, since its `Agent` subagents don't hit the same `opencode`-specific indexing bottleneck. |
