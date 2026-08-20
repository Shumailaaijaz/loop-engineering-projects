#!/usr/bin/env python3
"""Orchestrator for the Project 8 daily loop.

Wires the six Loop Engineering parts together for one chore: keeping
the monorepo root README.md's project index in sync with the
`project-N-*` directories that actually exist.

    Heartbeat (run_loop.sh / cron)
      -> Spine (this module + scripts/spine.py: run id, state, ledger)
        -> Worktree (git worktree add, isolated branch, always cleaned up)
          -> Skill (skills/readme-index/SKILL.md -- the procedure below follows it)
            -> Maker (scripts/maker.py)
              -> Checker (scripts/checker.py, run from THIS checkout, never
                          from inside the candidate worktree)
                -> Connector (scripts/connector.py: gh pr create, PASS only)

Required sequence (Phase 6 of the spec): budget guards and the
duplicate-execution lock are checked before any worktree is created;
the Connector is never called except after `checker.review().passed`
is True; every real run always records a ledger entry and cleans up
its worktree, regardless of outcome.

`run()` handles the cheap guards -- the duplicate-execution lock, the
STOP-file circuit breaker, the daily run budget -- and deliberately
does *not* write a ledger entry for them: they mean "no run happened",
which is a fact worth a log line (via spine.log) but not a run record.
`_execute()` is the actual run and always ends with exactly one ledger
entry, whatever the outcome.

Exit code: 0 for PUBLISHED or NOOP (healthy), 1 for anything else.
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import checker  # noqa: E402
import connector  # noqa: E402
import maker  # noqa: E402
import spine  # noqa: E402
from budget import BUDGET  # noqa: E402


class _Deadline(Exception):
    pass


def _alarm_handler(signum, frame):
    raise _Deadline("wall-clock runtime budget exceeded")


def _repo_root() -> Path:
    result = subprocess.run(
        ["git", "-C", str(spine.PROJECT8_DIR), "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(f"could not resolve repo root: {result.stderr.strip()}")
    return Path(result.stdout.strip())


def _git(repo_root: Path, *args, timeout=30):
    return subprocess.run(
        ["git", "-C", str(repo_root), *args], capture_output=True, text=True, timeout=timeout
    )


def _rev_parse(repo_root: Path, ref: str) -> str:
    r = _git(repo_root, "rev-parse", ref)
    if r.returncode != 0:
        raise RuntimeError(f"git rev-parse {ref} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def _cleanup_worktree(repo_root: Path, worktree_path: Path | None, branch: str | None) -> None:
    if worktree_path is not None and worktree_path.exists():
        _git(repo_root, "worktree", "remove", "--force", str(worktree_path))
        if worktree_path.exists():
            # Observed on this repo's /mnt/d (WSL 9p) mount: `git worktree
            # remove` successfully unregisters the worktree (git no longer
            # considers it one -- confirmed via `git worktree list`) but
            # can leave an empty directory behind. Not a correctness bug
            # (a fresh run-id never collides with it), but it would
            # otherwise accumulate one empty dir per run over a week.
            shutil.rmtree(worktree_path, ignore_errors=True)
    _git(repo_root, "worktree", "prune")
    if branch is not None:
        _git(repo_root, "branch", "-D", branch)  # ignored if already gone


def _new_run_id() -> str:
    return f"{spine.now_iso().replace(':', '').replace('-', '')}-{os.getpid()}"


def run(trigger: str) -> int:
    """Heartbeat entrypoint: cheap guards, then (at most) one logged run."""
    if not spine.acquire_lock():
        spine.log("duplicate execution prevented: another run is already in progress (lock held).")
        return 0
    try:
        stopped, stop_reason = spine.is_stopped()
        if stopped:
            spine.log(f"loop is STOPPED ({stop_reason}); no-op until a human clears state/STOP.")
            return 0

        sp = spine.load_spine()
        if spine.runs_today(sp) >= BUDGET.max_runs_per_day:
            spine.log(f"daily run budget ({BUDGET.max_runs_per_day}) already used today; skipping.")
            return 0
        sp = spine.record_run_started(sp)
        spine.save_spine(sp)

        return _execute(trigger, _new_run_id())
    finally:
        spine.release_lock()


def _execute(trigger: str, run_id: str) -> int:
    """One fully-logged run. Always ends with exactly one ledger entry."""
    status = "ERROR"
    reasons: list[str] = []
    pr_url = None
    branch = None
    worktree_path = None
    maker_result = {"changed": False, "missing": [], "added_lines": []}
    check_result = None
    attempts = 0
    start = time.monotonic()

    try:
        repo_root = _repo_root()
        signal.signal(signal.SIGALRM, _alarm_handler)
        signal.alarm(BUDGET.max_runtime_seconds)

        try:
            _git(repo_root, "worktree", "prune")
            base_sha = _rev_parse(repo_root, "HEAD")

            existing_pr = connector.find_existing_open_pr(repo_root)
            if existing_pr:
                status = "NOOP"
                reasons = [f"open PR already proposes this change: {existing_pr.get('url')}"]
                spine.log(f"run {run_id}: NOOP -- {reasons[0]}")
                return 0

            missing = maker.missing_projects(repo_root)
            if not missing:
                status = "NOOP"
                spine.log(f"run {run_id}: NOOP -- root README.md already lists every project directory.")
                return 0

            branch = f"{connector.BRANCH_PREFIX}{run_id}"
            worktree_path = spine.PROJECT8_DIR / ".worktrees" / run_id
            worktree_path.parent.mkdir(exist_ok=True)
            add = _git(repo_root, "worktree", "add", str(worktree_path), "-b", branch, base_sha)
            if add.returncode != 0:
                raise RuntimeError(f"git worktree add failed: {add.stderr.strip()}")

            for attempts in range(1, BUDGET.max_repair_attempts + 2):
                maker_result = maker.apply(worktree_path)
                if not maker_result["changed"]:
                    status = "NOOP"
                    spine.log(f"run {run_id}: NOOP -- no drift found on repair attempt {attempts}.")
                    return 0

                _git(worktree_path, "add", "README.md")
                commit = _git(
                    worktree_path, "commit", "-m",
                    f"Project 8 loop: sync root README project index ({run_id})",
                )
                if commit.returncode != 0:
                    raise RuntimeError(f"git commit failed: {commit.stderr.strip()}")
                head_sha = _rev_parse(worktree_path, "HEAD")

                check_result = checker.review(worktree_path, repo_root, base_sha, head_sha)
                if check_result.passed:
                    break
                spine.log(f"run {run_id}: Checker FAIL on attempt {attempts}: {check_result.reasons}")
                if attempts <= BUDGET.max_repair_attempts:
                    _git(worktree_path, "reset", "--hard", base_sha)

            if check_result is None or not check_result.passed:
                status = "FAIL"
                reasons = check_result.reasons if check_result else ["Checker never ran."]
                return 1

            pub = connector.publish(worktree_path, branch, run_id, maker_result["added_lines"])
            if not pub["published"]:
                status = "CONNECTOR_FAILED"
                reasons = [pub["reason"]]
                return 1

            status = "PUBLISHED"
            pr_url = pub["pr_url"]
            return 0

        finally:
            signal.alarm(0)

    except _Deadline as e:
        status = "BUDGET_EXCEEDED"
        reasons = [str(e)]
        return 1
    except Exception as e:  # noqa: BLE001 -- top-level safety net, never let the loop crash silently
        status = "ERROR"
        reasons = [f"{type(e).__name__}: {e}"]
        return 1
    finally:
        elapsed = round(time.monotonic() - start, 2)
        try:
            _cleanup_worktree(_repo_root(), worktree_path, branch)
        except Exception as cleanup_err:  # noqa: BLE001
            spine.log(f"run {run_id}: WARNING -- worktree cleanup failed: {cleanup_err}")

        sp = spine.load_spine()
        sp = spine.record_run_finished(sp, status)
        stopped_now = False
        if sp["consecutive_failures"] >= BUDGET.max_consecutive_failures:
            spine.write_stop(
                f"{sp['consecutive_failures']} consecutive non-success runs "
                f"(last status={status}, reasons={reasons})"
            )
            stopped_now = True
        spine.save_spine(sp)

        spine.append_ledger({
            "run_id": run_id,
            "timestamp_utc": spine.now_iso(),
            "trigger": trigger,
            "task": "root-readme-project-index",
            "branch": branch,
            "worktree": str(worktree_path) if worktree_path else None,
            "maker_result": maker_result,
            "checker_passed": check_result.passed if check_result else None,
            "checker_reasons": check_result.reasons if check_result else reasons,
            "checker_warnings": check_result.warnings if check_result else [],
            "tests": check_result.tests if check_result else [],
            "files_changed": check_result.files_changed if check_result else [],
            "lines_changed": check_result.lines_changed if check_result else 0,
            "repair_attempts": max(attempts - 1, 0),
            "runtime_seconds": elapsed,
            "pr_url": pr_url,
            "final_status": status,
            "circuit_breaker_tripped": stopped_now,
        })
        spine.log(
            f"run {run_id} finished: status={status} elapsed={elapsed}s "
            f"pr={pr_url} reasons={reasons}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trigger", default="manual", help="what invoked this run (cron, manual, dry-run)")
    args = parser.parse_args()
    return run(args.trigger)


if __name__ == "__main__":
    sys.exit(main())
