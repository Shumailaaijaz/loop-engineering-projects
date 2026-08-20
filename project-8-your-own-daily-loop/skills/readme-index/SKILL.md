---
name: readme-index
description: Standard maker-checker procedure for keeping the monorepo root README.md's project index in sync with the project-N-* directories that actually exist on disk.
---

# Skill: Root README Project Index (Maker-Checker)

This is the standard, narrow procedure for the one chore the Project 8
loop performs. It exists so that the root README.md never silently goes
stale as new `project-N-*` directories are added, and so that the fix
is never accepted on the Maker's own say-so.

## Exact task

Ensure `README.md` at the repository root contains one bullet line for
every top-level `project-N-*` directory. Nothing else.

## Allowed files

- **Read**: every `project-*` directory name at the repo root; each such
  project's own `README.md` (first heading line only, for a short
  description).
- **Write**: exactly one file — the repository root `README.md`. Only
  ever *append* new bullet lines under a `## Projects` heading (created
  if absent). Never edit, reorder, or remove a line that was already
  there.

## Forbidden files

- Any file other than the root `README.md`.
- Anything under `project-8-your-own-daily-loop/` itself (the loop must
  not modify its own code as part of doing its job).
- Any project's own `README.md` (read-only source of the description).

## Procedure

1. **Detect drift.** List `project-*` directories at the repo root.
   Read the current root `README.md`. A project is "missing" if its
   directory name does not appear anywhere in the current text.
2. **If nothing is missing, stop.** This is the common case (most days,
   nothing changed) and is a healthy `NOOP`, not a failure and not
   something requiring a worktree, a commit, or a PR.
3. **If something is missing, work only inside an isolated worktree.**
   `git worktree add .worktrees/<run-id> -b project8/readme-sync-<run-id>`
   off the current `main`. Never edit the root `README.md` directly on
   `main`.
4. **Draft the smallest correct patch.** For each missing project,
   append `- [project-N-name](project-N-name/README.md) — <first
   heading of that project's own README>` under `## Projects` (or
   `- project-N-name — (no project README found)` if that project has
   no README yet). Do not touch any other line in the file.
5. **Commit inside the worktree.** One commit, `README.md` only.
6. **Hand off to the Checker.** Give it the worktree path, the base
   commit, and the head commit. Do not summarize the change as "done" —
   the Checker recomputes everything itself; it does not trust this
   report.
7. **Only publish after Checker PASS.** A PR may be opened only once
   `scripts/checker.py` independently confirms: scope is `README.md`
   only, no existing line was removed or altered, every project
   directory is now referenced, no broken relative links were
   introduced, and the full repository test sweep is green. On `FAIL`,
   at most one bounded repair attempt is allowed before the run stops
   and reports failure — never retry indefinitely, and never weaken the
   Checker's own criteria to force a pass.

## Stop conditions

- No drift found → stop after step 2, no worktree needed.
- An open PR from a previous run already proposes this exact change →
  stop before creating a worktree (avoid a duplicate PR).
- Checker FAIL after the one bounded repair attempt → stop, publish
  nothing, record the failure.
- Any budget guard exceeded (runtime, files changed, lines changed,
  daily run count, consecutive-failure circuit breaker) → stop
  immediately, publish nothing. See `README.md` ("Budget Guards").

## Failure conditions

- The candidate diff touches any file other than the root `README.md`.
- Any existing line in the root `README.md` is missing from the
  candidate.
- A project directory is still not referenced after the patch.
- A newly added markdown link points at a file that does not exist.
- Any test in the repository's test sweep fails (regression).
