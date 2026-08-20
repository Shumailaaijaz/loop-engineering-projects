#!/usr/bin/env bash
# Heartbeat entrypoint. This is the only thing cron calls.
#
# All duplicate-execution prevention, the STOP-file circuit breaker, and
# the daily run budget are enforced inside scripts/loop.py itself (via
# scripts/spine.py) so that a manual run and a cron run go through
# exactly the same guards -- this wrapper does not duplicate that logic,
# it only picks the interpreter and makes sure output always lands
# somewhere durable even if cron's own logging is misconfigured.
set -uo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="$PROJECT_DIR/state"
mkdir -p "$STATE_DIR"

PYTHON_BIN="python3"
if [ -x "$HOME/.cache/loop-engineering-p5-pytest-venv/bin/python" ]; then
  PYTHON_BIN="$HOME/.cache/loop-engineering-p5-pytest-venv/bin/python"
fi

"$PYTHON_BIN" "$PROJECT_DIR/scripts/loop.py" --trigger cron \
  >> "$STATE_DIR/cron_stdout.log" 2>&1

exit $?
