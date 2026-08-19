#!/usr/bin/env bash
# The "OpenCode approach" to Project 5: codify the body of Project 4's
# maker-checker fix loop as one unattended shell script.
#
#   PHASE 1 (fan-out, parallel, isolated)
#     for each candidate:
#       git worktree add   -> its own branch + its own checkout
#       opencode run        -> an independent headless agent drafts a fix,
#                              scoped to that worktree only, edit-only
#                              permissions (config/opencode.jsonc)
#     & ... wait             -> all three run concurrently, we block until
#                              every one has finished (or timed out)
#
#   PHASE 2 (grade, sequential, independent)
#     for each candidate:
#       scripts/review_fix.py from Project 4 (unchanged, untouched by any
#       candidate) grades the diff against its own oracle test.
#       Its exit code (0/1) IS the checker -- no LLM judgement, no
#       "looks right to me". PASS/FAIL is read straight off $?.
#
# One command. No step-by-step prompting. Run it as many times as you
# like -- see the "no memory" note in ../README.md.
#
# MAKER_CLI picks which headless coding CLI drafts each candidate:
#   claude   (default) -- `claude -p --permission-mode acceptEdits`
#   opencode            -- `opencode run --model $MAKER_MODEL`
# Default is `claude`, not `opencode`, despite the name of this file and
# approach: while building this, the only configured opencode provider
# (Google Gemini, via $GOOGLE_API_KEY) hit its free-tier quota
# ("Quota exceeded ... generate_content_free_tier_requests, limit: 20")
# and stayed exhausted across models and cooldowns -- see the README for
# the full trail. The orchestration below (the for loop, the & / wait
# fan-out, the reviewer's exit code as the sole checker) is exactly
# what the exercise asks for either way; only which CLI plays "maker" is
# swappable. Set MAKER_CLI=opencode to use the original path once quota
# is available again.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
P5_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$P5_ROOT/.." && pwd)"
P4_DIR="project-4-fix-loop-With-Real-Checker"
P4_ROOT="$REPO_ROOT/$P4_DIR"
BASE_BRANCH="main"

CANDIDATES=(candidate-1 candidate-2 candidate-3)
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
# Worktree checkouts (44 files each, watched/indexed by opencode) live on
# native filesystem, not this repo's own /mnt/d mount -- WSL's 9p I/O on
# a Windows-mounted drive is slow enough that three concurrent opencode
# instances indexing their checkout there can eat an entire timeout
# before ever issuing a tool call. Evidence (small text logs) stays in
# the repo; only the checkouts themselves move.
WORKTREE_BASE="${WORKTREE_BASE:-$HOME/.cache/loop-engineering-p5-worktrees}"
WORKTREE_ROOT="$WORKTREE_BASE/$RUN_ID"
EVIDENCE_DIR="$P5_ROOT/evidence/opencode-run-$RUN_ID"
mkdir -p "$WORKTREE_ROOT" "$EVIDENCE_DIR"

MAKER_CLI="${MAKER_CLI:-claude}"
MAKER_MODEL="${MAKER_MODEL:-google/gemini-2.5-flash}"
MAKER_TIMEOUT="${MAKER_TIMEOUT:-180}"

export GOOGLE_GENERATIVE_AI_API_KEY="${GOOGLE_GENERATIVE_AI_API_KEY:-${GOOGLE_API_KEY:-}}"

# review_fix.py needs a python with pytest importable. Bootstrap one on
# first use so this script needs no manual setup step (a native-fs cache
# dir, since this repo lives on a slow /mnt/d mount -- see Project 4's
# README for why that matters).
if [ -z "${PYTEST_PYTHON:-}" ]; then
    VENV_HOME="${PYTEST_VENV:-$HOME/.cache/loop-engineering-p5-pytest-venv}"
    if ! "$VENV_HOME/bin/python" -c "import pytest" >/dev/null 2>&1; then
        echo "Bootstrapping a pytest-capable interpreter at $VENV_HOME ..."
        python3 -m venv "$VENV_HOME" >/dev/null
        "$VENV_HOME/bin/pip" install -q pytest >/dev/null
    fi
    export PYTEST_PYTHON="$VENV_HOME/bin/python"
fi

read -r -d '' DRAFT_PROMPT <<'EOF' || true
You are the implementer in a maker-checker bug-fix procedure. You are
working alone in your own isolated git worktree; other candidates are
attempting the same fix independently in their own worktrees and cannot
see your work, and you cannot see theirs.

Read BUG_REPORT.md and skills/fix-bug/SKILL.md in the current directory
for full context and the required procedure.

Fix the bug in app/inventory.py: remove_duplicates() must preserve the
order items were first seen, not just remove duplicates (list(set(...))
is the bug -- set() does not preserve insertion order).

Add or update a regression test in app/test_inventory.py that checks the
exact expected output order, not a weakened check like "no duplicates"
or sorted() that would pass for the wrong reason.

Only touch files under app/. Do not modify anything under reviewer/,
scripts/, skills/, or opencode.jsonc -- you are not the reviewer and
must not be able to influence how you are graded.

Do not run the test suite yourself and do not declare the fix correct --
an independent reviewer grades this after you stop. Just make the
change and stop.
EOF

section() { printf '\n=== %s ===\n' "$*"; }

section "Run $RUN_ID -- Phase 1: drafting ${#CANDIDATES[@]} candidates in parallel, isolated worktrees"

for name in "${CANDIDATES[@]}"; do
    (
        branch="project5/${name}-${RUN_ID}"
        wt_path="$WORKTREE_ROOT/$name"
        log_file="$EVIDENCE_DIR/$name.log"
        proj_dir="$wt_path/$P4_DIR"

        {
            echo "--- worktree setup ($branch) ---"
            git -C "$P4_ROOT" worktree add "$wt_path" -b "$branch" "$BASE_BRANCH"
        } >"$log_file" 2>&1

        if [ "$MAKER_CLI" = "opencode" ]; then
            cp "$P5_ROOT/config/opencode.jsonc" "$proj_dir/opencode.jsonc"

            # opencode keeps its session state in a single shared sqlite db
            # under $XDG_DATA_HOME/opencode by default. Running three
            # instances against that one file concurrently deadlocks it
            # ("database is locked"). Giving each candidate its own
            # XDG_DATA_HOME gives it its own db and makes the fan-out truly
            # parallel instead of accidentally serialized-and-broken.
            candidate_data_home="$wt_path/.opencode-data"
            mkdir -p "$candidate_data_home"

            {
                echo
                echo "--- maker (opencode run, model=$MAKER_MODEL, timeout=${MAKER_TIMEOUT}s) ---"
                cd "$proj_dir" && XDG_DATA_HOME="$candidate_data_home" \
                    timeout "$MAKER_TIMEOUT" opencode run "$DRAFT_PROMPT" --model "$MAKER_MODEL"
                echo "(maker exit code: $?)"
            } >>"$log_file" 2>&1

            # The permission profile was scaffolding for the maker, not part
            # of its fix -- drop it before committing so the reviewer's
            # app/-only scope check judges the fix, not our harness.
            rm -f "$proj_dir/opencode.jsonc"
        else
            {
                echo
                echo "--- maker (claude -p --permission-mode acceptEdits, timeout=${MAKER_TIMEOUT}s) ---"
                cd "$proj_dir" && timeout "$MAKER_TIMEOUT" claude -p "$DRAFT_PROMPT" \
                    --permission-mode acceptEdits \
                    --allowedTools "Edit Write Read Glob Grep"
                echo "(maker exit code: $?)"
            } >>"$log_file" 2>&1
        fi

        {
            echo
            echo "--- committing candidate's working-tree changes ---"
            git -C "$proj_dir" add app/
            git -C "$proj_dir" commit -m "candidate $name: automated draft fix ($RUN_ID)" --quiet \
                && echo "(committed)" || echo "(nothing to commit)"
            echo "--- diff vs $BASE_BRANCH ---"
            git -C "$proj_dir" diff --stat "$BASE_BRANCH...HEAD"
        } >>"$log_file" 2>&1
    ) &
done
wait

section "Phase 1 complete"

section "Phase 2: reviewer verdicts (Project 4's scripts/review_fix.py -- exit code is the checker)"

declare -A VERDICT
for name in "${CANDIDATES[@]}"; do
    proj_dir="$WORKTREE_ROOT/$name/$P4_DIR"
    verdict_log="$EVIDENCE_DIR/$name.verdict.log"
    if python3 "$P4_ROOT/scripts/review_fix.py" --worktree "$proj_dir" --base "$BASE_BRANCH" \
        >"$verdict_log" 2>&1; then
        VERDICT[$name]="PASS"
    else
        VERDICT[$name]="FAIL"
    fi
    echo "$name: ${VERDICT[$name]}  (full verdict: evidence/opencode-run-$RUN_ID/$name.verdict.log)"
done

section "Run $RUN_ID summary"
{
    printf '%-14s %-6s %s\n' "candidate" "verdict" "worktree"
    for name in "${CANDIDATES[@]}"; do
        printf '%-14s %-6s %s\n' "$name" "${VERDICT[$name]}" "$WORKTREE_ROOT/$name/$P4_DIR"
    done
} | tee "$EVIDENCE_DIR/summary.txt"

any_pass=0
for name in "${CANDIDATES[@]}"; do
    [ "${VERDICT[$name]}" = "PASS" ] && any_pass=1
done

if [ "$any_pass" = "1" ]; then
    echo "Result: at least one candidate PASSED -- PR gate open for it."
    exit 0
else
    echo "Result: no candidate passed -- PR gate stays closed."
    exit 1
fi
