import json
import shutil
import subprocess
import time

import pytest

import checker
import connector
import loop
import maker
from budget import Budget


def _git(cmd, cwd):
    return subprocess.run(["git", "-C", str(cwd), *cmd], capture_output=True, text=True)


def _read_ledger(project8_dir):
    path = project8_dir / "state" / "ledger.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _read_spine(project8_dir):
    return json.loads((project8_dir / "state" / "spine.json").read_text())


def test_normal_successful_run(monkeypatch, loop_env):
    repo, project8_dir, spine_mod = loop_env
    monkeypatch.setattr(connector, "find_existing_open_pr", lambda repo_root: None)
    monkeypatch.setattr(
        connector, "publish",
        lambda worktree_root, branch, run_id, added_lines: {
            "published": True, "pr_url": "https://example.invalid/pr/1", "reason": None
        },
    )

    exit_code = loop.run("test")

    assert exit_code == 0
    entries = _read_ledger(project8_dir)
    assert len(entries) == 1
    assert entries[0]["final_status"] == "PUBLISHED"
    assert entries[0]["pr_url"] == "https://example.invalid/pr/1"
    assert entries[0]["checker_passed"] is True

    sp = _read_spine(project8_dir)
    assert sp["total_runs"] == 1
    assert sp["consecutive_failures"] == 0

    # Worktree isolation: main's checkout is untouched, worktree cleaned up.
    assert "project-2-beta" not in (repo / "README.md").read_text()
    assert not any((project8_dir / ".worktrees").glob("*"))
    branches = _git(["branch", "--list", "project8/readme-sync-*"], repo).stdout
    assert branches.strip() == ""


def test_maker_failure_records_error_and_does_not_publish(monkeypatch, loop_env):
    repo, project8_dir, spine_mod = loop_env

    def boom(_wt):
        raise RuntimeError("maker exploded")

    monkeypatch.setattr(maker, "apply", boom)
    publish_calls = []
    monkeypatch.setattr(
        connector, "publish",
        lambda *a, **k: publish_calls.append(1) or {"published": True, "pr_url": "x", "reason": None},
    )

    exit_code = loop.run("test")

    assert exit_code == 1
    assert publish_calls == []
    entries = _read_ledger(project8_dir)
    assert entries[0]["final_status"] == "ERROR"
    assert "maker exploded" in entries[0]["checker_reasons"][0]
    assert not any((project8_dir / ".worktrees").glob("*"))


def test_checker_rejection_blocks_publish_and_bounds_retries(monkeypatch, loop_env):
    repo, project8_dir, spine_mod = loop_env
    call_count = {"n": 0}

    def always_fail(*args, **kwargs):
        call_count["n"] += 1
        return checker.CheckResult(passed=False, reasons=["forced rejection"])

    monkeypatch.setattr(checker, "review", always_fail)
    publish_calls = []
    monkeypatch.setattr(connector, "publish", lambda *a, **k: publish_calls.append(1))

    exit_code = loop.run("test")

    assert exit_code == 1
    assert publish_calls == []
    assert call_count["n"] == 2  # 1 initial attempt + 1 bounded repair attempt
    entries = _read_ledger(project8_dir)
    assert entries[0]["final_status"] == "FAIL"
    assert entries[0]["repair_attempts"] == 1
    assert entries[0]["checker_reasons"] == ["forced rejection"]


def test_preexisting_unrelated_test_failure_does_not_block_a_docs_only_publish(monkeypatch, loop_env):
    # A test failure elsewhere in the repo, provably unaffected by a
    # README-only diff, must not block this chore -- it's not this
    # candidate's fault. The loop should still publish, with the failure
    # visible as a warning, not hidden and not blocking.
    repo, project8_dir, spine_mod = loop_env
    broken = repo / "project-3-gamma"
    broken.mkdir()
    (broken / "test_broken.py").write_text("def test_x():\n    assert False\n")
    _git(["add", "-A"], repo)
    _git(["commit", "-m", "add broken project"], repo)

    monkeypatch.setattr(connector, "find_existing_open_pr", lambda repo_root: None)
    monkeypatch.setattr(
        connector, "publish",
        lambda *a, **k: {"published": True, "pr_url": "https://example.invalid/pr/3", "reason": None},
    )

    exit_code = loop.run("test")

    assert exit_code == 0
    entries = _read_ledger(project8_dir)
    assert entries[0]["final_status"] == "PUBLISHED"
    assert entries[0]["checker_passed"] is True


def test_maker_writes_outside_readme_are_never_committed(monkeypatch, loop_env):
    # loop.py stages exactly README.md before committing (never `git add
    # -A`) -- so even if a Maker implementation wrote to another file, that
    # write can never reach the candidate commit checker.py evaluates.
    # This is structural defense-in-depth: the scope violation the Checker
    # is built to catch (see test_checker.py) can't actually occur through
    # this orchestrator. Proven here by tampering with an unrelated file
    # and confirming the run still succeeds on README.md alone, with the
    # tampering left an uncommitted, harmless stray change in a worktree
    # that gets deleted anyway.
    repo, project8_dir, spine_mod = loop_env
    original_apply = maker.apply

    def tampering_apply(wt):
        result = original_apply(wt)
        (wt / "project-1-alpha" / "README.md").write_text("# Project 1: Alpha\n\ntampered\n")
        return result

    monkeypatch.setattr(maker, "apply", tampering_apply)
    monkeypatch.setattr(connector, "find_existing_open_pr", lambda repo_root: None)
    monkeypatch.setattr(
        connector, "publish",
        lambda *a, **k: {"published": True, "pr_url": "https://example.invalid/pr/4", "reason": None},
    )

    exit_code = loop.run("test")

    assert exit_code == 0
    entries = _read_ledger(project8_dir)
    assert entries[0]["final_status"] == "PUBLISHED"
    assert entries[0]["files_changed"] == ["README.md"]
    # The tampered file was never committed to main either way.
    assert (repo / "project-1-alpha" / "README.md").read_text() == "# Project 1: Alpha\n\nFirst project.\n"


def test_budget_exhaustion_blocks_publish(monkeypatch, loop_env):
    repo, project8_dir, spine_mod = loop_env
    monkeypatch.setattr(checker, "BUDGET", Budget(max_lines_changed=0))

    exit_code = loop.run("test")

    assert exit_code == 1
    entries = _read_ledger(project8_dir)
    assert entries[0]["final_status"] == "FAIL"
    assert any("exceeds budget" in r for r in entries[0]["checker_reasons"])


def test_timeout_trips_budget_exceeded(monkeypatch, loop_env):
    repo, project8_dir, spine_mod = loop_env
    monkeypatch.setattr(loop, "BUDGET", Budget(max_runtime_seconds=1))

    def slow_apply(wt):
        time.sleep(3)
        return {"changed": True, "missing": ["project-2-beta"], "added_lines": ["- project-2-beta"]}

    monkeypatch.setattr(maker, "apply", slow_apply)

    exit_code = loop.run("test")

    assert exit_code == 1
    entries = _read_ledger(project8_dir)
    assert entries[0]["final_status"] == "BUDGET_EXCEEDED"
    assert not any((project8_dir / ".worktrees").glob("*"))


def test_connector_failure_is_recorded_and_not_fatal_to_the_loop(loop_env):
    if shutil.which("gh") is None:
        pytest.skip("gh CLI not available in this environment")
    repo, project8_dir, spine_mod = loop_env
    # find_existing_open_pr and publish both run for real here: origin is a
    # local bare repo, so `git push` succeeds (no network needed) but
    # `gh pr create` genuinely fails (no real GitHub repository to open a
    # PR against) -- a real, unmocked connector failure.
    exit_code = loop.run("test")

    assert exit_code == 1
    entries = _read_ledger(project8_dir)
    assert entries[0]["final_status"] == "CONNECTOR_FAILED"
    assert entries[0]["checker_passed"] is True  # Checker approved; only publishing failed
    pushed_branches = _git(["branch", "--list", "project8/readme-sync-*"], repo.parent / "origin.git").stdout
    assert "project8/readme-sync-" in pushed_branches  # push half of Connector did succeed


def test_duplicate_execution_prevention(loop_env):
    repo, project8_dir, spine_mod = loop_env
    assert spine_mod.acquire_lock() is True  # simulate another run already holding the lock
    try:
        exit_code = loop.run("test")
        assert exit_code == 0
        assert _read_ledger(project8_dir) == []
    finally:
        spine_mod.release_lock()


def test_safe_stop_behavior(loop_env):
    repo, project8_dir, spine_mod = loop_env
    spine_mod.write_stop("manually triggered for test")

    exit_code = loop.run("test")

    assert exit_code == 0
    assert _read_ledger(project8_dir) == []  # STOP short-circuits before any run is recorded
    assert not any((project8_dir / ".worktrees").glob("*"))


def test_circuit_breaker_trips_after_max_consecutive_failures(monkeypatch, loop_env):
    repo, project8_dir, spine_mod = loop_env
    monkeypatch.setattr(
        checker, "review",
        lambda *a, **k: checker.CheckResult(passed=False, reasons=["forced"]),
    )
    test_budget = Budget(max_consecutive_failures=2, max_repair_attempts=0, max_runs_per_day=10)
    monkeypatch.setattr(loop, "BUDGET", test_budget)
    monkeypatch.setattr(checker, "BUDGET", test_budget)

    assert loop.run("test") == 1
    assert not (project8_dir / "state" / "STOP").exists()
    assert loop.run("test") == 1
    assert (project8_dir / "state" / "STOP").exists()

    # A third invocation must be a pure no-op: STOP wins before anything else runs.
    entries_before = _read_ledger(project8_dir)
    assert loop.run("test") == 0
    assert _read_ledger(project8_dir) == entries_before


def test_stale_worktree_registration_does_not_crash_a_fresh_run(monkeypatch, loop_env):
    repo, project8_dir, spine_mod = loop_env
    orphan_branch = "project8/readme-sync-orphan"
    orphan_path = project8_dir / ".worktrees" / "orphan"
    orphan_path.parent.mkdir(parents=True, exist_ok=True)
    _git(["worktree", "add", str(orphan_path), "-b", orphan_branch], repo)
    shutil.rmtree(orphan_path)  # simulate a crash: directory gone, git metadata still thinks it's there

    monkeypatch.setattr(connector, "find_existing_open_pr", lambda repo_root: None)
    monkeypatch.setattr(
        connector, "publish",
        lambda *a, **k: {"published": True, "pr_url": "https://example.invalid/pr/2", "reason": None},
    )

    exit_code = loop.run("test")

    assert exit_code == 0
    entries = _read_ledger(project8_dir)
    assert entries[0]["final_status"] == "PUBLISHED"
