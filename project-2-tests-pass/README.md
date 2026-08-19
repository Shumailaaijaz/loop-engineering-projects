# Project 2 — Make the Test Pass, Then Stop

## Project goal

This project is a small, self-contained demonstration of a **conditional
loop** built around the **Maker-Checker pattern**. It shows how an AI
coding agent can be put to work fixing code, while an independent,
mechanical test runner — not the agent's own opinion — decides when the
work is actually finished.

## The Maker-Checker pattern

- **Maker** — the coding agent (Claude, invoked headlessly via
  `claude -p` from `loop.sh`). Its job is to *modify `app.py`* to try to
  fix the failing tests. It is given the failing pytest output and
  nothing more.
- **Checker** — `pytest`, running against `test_app.py`. It independently
  verifies whether the Maker's change actually works. It has no opinion
  about the code beyond "did the assertions pass or fail."

The Maker never gets to grade its own homework. The Checker does.

## Why the agent is not trusted to declare completion

AI agents can be confidently wrong. An agent might edit `app.py`, glance
at the diff, and say "looks good, this should work now" — without that
claim being true. If we let statements like *"the task is complete"* or
*"I think it works"* stop the loop, a broken implementation could be
reported as done.

Instead, `loop.sh` never asks the agent whether it's finished. It only
asks one machine-checkable question: **did `pytest` exit with code 0?**

## How pytest acts as the external checker

Each iteration, `loop.sh` runs:

```bash
python -m pytest -q
```

and inspects `$?`, the process exit code:

- `pytest` exits **0** when every test in `test_app.py` passes.
- `pytest` exits **non-zero** (1) when any test fails.

This exit code is the *only* signal the loop trusts.

## How the exit code determines continuation or stopping

```
if exit_code == 0:
    stop the loop, report SUCCESS
else:
    hand the failing pytest output to the Maker for a fix
    continue to the next attempt
```

There is no branch anywhere in `loop.sh` that stops the loop because the
agent "believes" it is done. The only successful exit path runs through
a `pytest` exit code of `0`.

## Why the loop has a maximum of 6 attempts

The 6-attempt cap is a **safety limit**, not a completion condition. It
exists so that a genuinely broken loop (e.g. the agent repeatedly
producing bad fixes, or `claude` being unavailable) fails loudly and
exits non-zero instead of spinning forever. Reaching attempt 6 is always
reported as a **failure** — it never counts as success, even though the
loop stops.

## How to run the project

```bash
# run from this project's root folder

# one-time setup: create a virtualenv with pytest installed
python3 -m venv .venv
.venv/bin/pip install pytest

# run the tests directly (Checker only, no Maker)
.venv/bin/python -m pytest -q

# run the full Maker-Checker loop
./loop.sh
```

`loop.sh` will use `.venv/bin/python` automatically if the virtualenv
exists, otherwise it falls back to `python3` on the `PATH`. It calls the
`claude` CLI (headless `claude -p` mode) as the Maker when tests fail; if
`claude` isn't installed, the loop still runs and correctly reports
failure/attempts, it just can't auto-fix the code for you.

## Example successful output

```
Attempt 1/6
Running tests...
FFF
...
Tests failed.
Sending failure information for correction...

Attempt 2/6
Running tests...
...
Tests passed.

✓ Checker passed.
✓ Work is complete.
✓ Stopping loop.
```

## Example failed-after-6-attempts output

```
Attempt 6/6
Running tests...
FFF
...
Tests failed.

Attempt 6/6
Tests still failing.
✗ Maximum attempts reached.
✗ Work is NOT verified as complete.
```

`loop.sh` exits with status `1` in this case (and `0` on success), so it
composes cleanly with CI or any other script that checks `$?`.

## What this project demonstrates about Loop Engineering

- **Conditional loops beat fixed loops.** The loop stops the moment the
  real condition (`pytest` exit code `0`) is met — it does not blindly
  run all 6 attempts every time.
- **Verification must be external to the agent.** The party doing the
  work (Maker) and the party judging the work (Checker) must be
  different, or "done" becomes whatever the agent feels like claiming.
- **Bounded retries protect against runaway loops.** A max-attempt safety
  cap turns an infinite/unbounded loop into a process that always
  terminates, while still treating "hit the cap" as failure, not success.
- **Machine-checkable success criteria are what make autonomy safe.**
  Exit codes, not prose, are what a loop should branch on.
