#!/usr/bin/env bash
# Demonstration harness for Project 4: worktree + skill + maker-checker.
#
# Pipeline:
#
#   REAL BUG
#      |
#   FIX SKILL (skills/fix-bug/SKILL.md)
#      |
#   IMPLEMENTER (works only inside an isolated git worktree)
#      |
#   ISOLATED WORKTREE (project4/<name> branch, .worktrees/<name>)
#      |
#   CODE + TESTS
#      |
#   REVIEWER (scripts/review_fix.py — independent, owns its own oracle test)
#      |
#   PASS ---------> PR gate allowed -> gh pr create
#      |
#      FAIL --------> PR gate blocked, fix or reject
#
# Requires the branches project4/good-fix and project4/bad-fix to already
# exist (created per skills/fix-bug/SKILL.md). This script does not write
# fixes itself — it drives the review + PR gate for whatever is already on
# those branches, exactly like a human/CI would.
set -uo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

BASE_BRANCH="main"
WORKTREE_DIR=".worktrees"

section() {
    echo
    echo "=== $1 ==="
}

ensure_worktree() {
    local name="$1"
    local branch="project4/$name"
    local path="$WORKTREE_DIR/$name"

    if ! git show-ref --verify --quiet "refs/heads/$branch"; then
        echo "Branch $branch does not exist yet. Create it per skills/fix-bug/SKILL.md first." >&2
        return 1
    fi

    if [ ! -d "$path" ]; then
        git worktree add "$path" "$branch" >/dev/null
    fi
    echo "$path"
}

run_path() {
    local name="$1"
    section "Path: $name (branch project4/$name)"

    local path
    path="$(ensure_worktree "$name")" || return 1

    echo "Worktree: $path"
    echo
    echo "--- git diff vs $BASE_BRANCH ---"
    git -C "$path" diff --stat "$BASE_BRANCH...HEAD"

    echo
    echo "--- reviewer verdict ---"
    if python3 scripts/review_fix.py --worktree "$path" --base "$BASE_BRANCH"; then
        echo
        echo "PR gate: PASS -> PR creation allowed."
        echo "Command that would open the PR:"
        echo "  gh pr create --base $BASE_BRANCH --head project4/$name --title \"Fix: preserve order in remove_duplicates\" --body \"See BUG_REPORT.md. Reviewer verdict: PASS.\""
        if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
            echo "(gh is authenticated in this environment — run the command above manually to open the PR.)"
        else
            echo "PR blocked because GitHub authentication/permissions are unavailable."
        fi
    else
        echo
        echo "PR gate: FAIL -> PR creation forbidden. No PR command will be shown or run."
    fi
}

run_path "good-fix"
run_path "bad-fix"
