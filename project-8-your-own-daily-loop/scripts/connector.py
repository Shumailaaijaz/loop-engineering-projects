"""Connector for the Project 8 daily loop.

Publishes a Checker-approved candidate as a real GitHub pull request via
`gh`, mirroring the Project 4 PR gate exactly: `gh pr create` is only
ever reached after an independent PASS. This module has no code path
that can be called on a FAIL -- loop.py enforces that by only calling
`publish()` after `checker.review().passed` is True.

The Connector never merges. It opens a PR against `main` and stops --
same as Project 4's PR #1 and Project 6's reviewed-but-unmerged PR #2.
A human decides whether to merge.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

BRANCH_PREFIX = "project8/readme-sync-"
PR_TITLE = "Project 8 loop: sync root README project index"


def _run(cmd, cwd=None, timeout=60):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def find_existing_open_pr(repo_root: Path) -> dict | None:
    """Return the first open PR from a previous run of this loop, if any.

    Used as a duplicate-publication guard: if yesterday's proposal is
    still open and unmerged, main hasn't changed, so today's drift
    detection would find the exact same missing entries and otherwise
    open a second, redundant PR proposing the identical diff.
    """
    result = _run(
        [
            "gh", "pr", "list",
            "--state", "open",
            "--json", "headRefName,url,number",
            "--limit", "50",
        ],
        cwd=str(repo_root),
    )
    if result.returncode != 0:
        return None  # gh unavailable/unauthenticated -- caller treats as "unknown, proceed"
    try:
        prs = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    for pr in prs:
        if pr.get("headRefName", "").startswith(BRANCH_PREFIX):
            return pr
    return None


def publish(worktree_root: Path, branch: str, run_id: str, added_lines: list[str]) -> dict:
    """Push `branch` and open a PR. Only ever called after a Checker PASS.

    Returns {"published": bool, "pr_url": str|None, "reason": str|None}.
    A push or PR-create failure is reported, never raised past this
    function and never retried here -- loop.py records it as a
    CONNECTOR_FAILED run and a human investigates before the next run.
    """
    push = _run(["git", "-C", str(worktree_root), "push", "-u", "origin", branch], timeout=60)
    if push.returncode != 0:
        return {"published": False, "pr_url": None, "reason": f"git push failed: {push.stderr.strip()}"}

    body_lines = [
        "Automated by the Project 8 daily loop (Maker: scripts/maker.py, "
        "Checker: scripts/checker.py, both independently re-run and passing).",
        "",
        f"Run ID: `{run_id}`",
        "",
        "New root README.md entries:",
        "",
        *added_lines,
        "",
        "This PR was opened only after an independent Checker verified: scope "
        "is README.md only, no existing line was removed or altered, every "
        "project directory is now referenced, no broken links were introduced, "
        "and the full repository test sweep is green. See "
        "project-8-your-own-daily-loop/state/ledger.jsonl for the full run record.",
    ]
    create = _run(
        [
            "gh", "pr", "create",
            "--base", "main",
            "--head", branch,
            "--title", PR_TITLE,
            "--body", "\n".join(body_lines),
        ],
        cwd=str(worktree_root),
        timeout=60,
    )
    if create.returncode != 0:
        return {
            "published": False,
            "pr_url": None,
            "reason": f"gh pr create failed: {create.stderr.strip() or create.stdout.strip()}",
        }
    pr_url = create.stdout.strip().splitlines()[-1] if create.stdout.strip() else None
    return {"published": True, "pr_url": pr_url, "reason": None}
