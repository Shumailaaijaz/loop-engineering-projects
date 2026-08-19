# Project 6 — The Doorbell Loop

Demonstrates an **event-driven GitHub pull-request review loop** using a
**Claude Code Routine** with a **GitHub `pull_request` webhook trigger** — not
a manual invocation, and not the OpenCode GitHub App approach.

The requirement this project proves: **the reviewer is never asked to review
by a human.** A GitHub PR event (opened / synchronize) is the only thing that
starts a review.

## Concepts demonstrated

- **Concept 7 — Event-driven loops**: the loop has no polling and no timer.
  It sits idle until GitHub fires a webhook, then runs once and stops.
- **Concept 10 — Connectors**: the Claude GitHub App is the connector between
  GitHub's event stream and a Claude Code cloud session.
- **GitHub as the external event source**, and **PR events as the heartbeat**:
  each `opened` or `synchronize` event is one heartbeat; two heartbeats in
  this project prove the loop re-fires rather than running once and going
  stale.

## Event flow

```text
GitHub PR opened
      │
      ▼
GitHub pull_request.opened event ──► Claude GitHub App ──► webhook trigger
      │
      ▼
Claude Code Routine fires (new cloud session, fresh clone)
      │
      ▼
Reviewer reads REVIEWER.md + the PR diff independently, runs pytest
      │
      ▼
Review posted automatically via `gh pr review`
      │
      ▼
Developer pushes a correction commit to the same PR branch
      │
      ▼
GitHub pull_request.synchronize event
      │
      ▼
Routine fires again (new, independent session)
      │
      ▼
Reviewer checks the updated code and posts a second review
```

## Repository layout

```text
project-6-doorbell-loop/
├── app/discount.py          # tiered-discount function under review
├── tests/test_discount.py   # boundary-focused test suite (9 tests)
├── REVIEWER.md              # reviewer spec: what "correct" means, what the
│                             # automatic reviewer must independently check
├── routine/routine-prompt.md# exact prompt stored on the live Routine
├── evidence/                # real, captured evidence of the event loop
└── README.md                # this file
```

## The codebase under review

`app/discount.py` implements a tiered quantity discount:

| quantity | discount |
|---|---|
| `< 5`   | 0% |
| `>= 5`  | 10% |
| `>= 10` | 20% |

Boundary quantities (exactly `5`, exactly `10`) belong to the **higher**
tier — this is documented in the module docstring, `REVIEWER.md`, and the
tests, and it's exactly where the planted bug lives (see below).

## The Claude Code Routine

Configured via the `RemoteTrigger` API (`claude.ai/code/routines`), **not**
`opencode github install`.

- **Routine**: `Project 6 - Doorbell Loop PR Reviewer`
  (`trig_01PiFmfdaYgN8JdpA33xYXLJ`) — https://claude.ai/code/routines/trig_01PiFmfdaYgN8JdpA33xYXLJ
- **Repository source**: `https://github.com/Shumailaaijaz/loop-engineering-projects`
- **Model**: `claude-sonnet-5`
- **Tools**: `Bash`, `Read`, `Grep`, `Glob` (enough to run `gh`, `pytest`, and
  read the diff — nothing else)
- **MCP connectors**: none (explicitly cleared — the reviewer needs no
  external services)
- **Trigger**: GitHub webhook trigger, `hook_type: app`, `source: github`,
  `scope_id: github.com/shumailaaijaz/loop-engineering-projects`,
  `events: [pull_request.opened, pull_request.synchronize]`

The full prompt is committed at [`routine/routine-prompt.md`](routine/routine-prompt.md).
It instructs Claude to: identify the triggering PR via `gh pr list`, read
`REVIEWER.md`, read the actual diff (never trust the PR description or the
author's own tests), hand-trace the boundary values, run the real test suite,
and post a real `gh pr review` (never a merge, never a bare "LGTM").

### A required manual step (documented limitation)

Creating the routine and the webhook trigger is fully done via API. **One
step cannot be done via API**: GitHub requires a human to install the
[Claude GitHub App](https://github.com/apps/claude) on the target repository
before it will deliver webhook events — this is GitHub's own consent screen,
not a Claude Code limitation. The first `create_webhook_trigger` call failed
with `github_app_not_installed` until this was done manually; see
[`evidence/01-routine-trigger.json`](evidence/01-routine-trigger.json) for
the exact before/after API responses. No other part of the trigger was faked
or simulated.

## The planted bug

Branch: `project6/planted-bug`. See [`evidence/`](evidence/) for the PR and
review capture, and the PR diff itself on GitHub for the exact change.

## Evidence

| File | What it shows |
|---|---|
| `evidence/01-routine-trigger.json` | Real API responses: routine creation, GitHub App install requirement, webhook trigger creation |
| `evidence/02-planted-bug-pr.*` | The planted-bug PR as opened, before any review existed |
| `evidence/03-automatic-review.*` | The first review, posted without any manual review request |
| `evidence/04-bug-detected.*` | The review comment/body identifying the planted bug, with file/line and fix |
| `evidence/05-synchronize-event.*` | The follow-up commit + GitHub's `synchronize` event on the same PR |
| `evidence/06-second-review.*` | The second automatic review, triggered purely by the `synchronize` event |

All evidence is real — captured from the live GitHub PR and the live Routine
run history (`RemoteTrigger` → `list_runs` / `get_run_log`), not fabricated
or manually triggered.

## Safety

- The demonstration PR is **not merged**.
- No force-push, no repo deletion, no secrets committed.
- The reviewer was never manually invoked; every review in `evidence/` was
  produced by a GitHub `pull_request` event firing the Routine.
