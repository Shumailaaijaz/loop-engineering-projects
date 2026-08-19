#!/usr/bin/env bash
#
# loop.sh — Maker-Checker conditional loop
#
# Checker : pytest (external, authoritative test runner)
# Maker   : the Claude Code CLI, invoked headlessly to patch app.py
#
# The loop's ONLY stopping conditions are:
#   1. pytest exits 0            -> SUCCESS, stop immediately.
#   2. MAX_ATTEMPTS is reached   -> FAILURE, stop with non-zero exit.
#
# The agent's own opinion about whether the code "looks correct" is
# never consulted. Only the exit code of `pytest` decides.

set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

MAX_ATTEMPTS=6
PYTHON_BIN="python3"
if [ -x ".venv/bin/python" ]; then
    PYTHON_BIN=".venv/bin/python"
fi

attempt=1
success=0

while [ "$attempt" -le "$MAX_ATTEMPTS" ]; do
    echo ""
    echo "Attempt ${attempt}/${MAX_ATTEMPTS}"
    echo "Running tests..."

    test_output=$("$PYTHON_BIN" -m pytest -q 2>&1)
    exit_code=$?

    echo "$test_output"

    # --- Checker decision point ---------------------------------------
    # The ONLY thing that determines success is this exit code.
    if [ "$exit_code" -eq 0 ]; then
        echo "Tests passed."
        echo ""
        echo "✓ Checker passed."
        echo "✓ Work is complete."
        echo "✓ Stopping loop."
        success=1
        break
    fi
    # --------------------------------------------------------------------

    echo "Tests failed."

    if [ "$attempt" -eq "$MAX_ATTEMPTS" ]; then
        # Do not call the Maker on the final attempt; we are stopping anyway.
        break
    fi

    echo "Sending failure information for correction..."

    if command -v claude >/dev/null 2>&1; then
        # --- Maker step -------------------------------------------------
        # The coding agent (Claude) is given ONLY the failing test output
        # and asked to fix app.py. It cannot decide the loop is done; it
        # can only attempt a fix, which the next loop iteration re-checks.
        claude -p "The following pytest run failed for the project in $(pwd).
Fix ONLY app.py so that all tests in test_app.py pass.
Do not modify test_app.py. Do not add extra files.
Make the smallest correct change.

pytest output:
${test_output}
" --allowedTools "Read,Edit,Write" >/dev/null 2>&1
        # ------------------------------------------------------------------
    else
        echo "(claude CLI not found — cannot auto-fix; see README.md)"
    fi

    attempt=$((attempt + 1))
done

echo ""
if [ "$success" -eq 1 ]; then
    exit 0
else
    echo "Attempt ${MAX_ATTEMPTS}/${MAX_ATTEMPTS}"
    echo "Tests still failing."
    echo "✗ Maximum attempts reached."
    echo "✗ Work is NOT verified as complete."
    exit 1
fi
