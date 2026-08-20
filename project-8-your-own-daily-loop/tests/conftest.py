"""Shared fixtures for the Project 8 loop tests.

Every test runs against a throwaway git repo under pytest's tmp_path --
never against the real monorepo. spine.py's module-level path constants
are monkeypatched to point inside that throwaway repo so loop.py's
Spine, Worktree, and lock/STOP-file logic all operate on test-only
files.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


def _run(cmd, cwd):
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    assert result.returncode == 0, f"{cmd} failed: {result.stderr}"
    return result


@pytest.fixture
def repo_factory(tmp_path):
    """Build a throwaway git repo with a root README.md and two project
    dirs, plus a bare 'origin' remote so `git push` works with no network.
    Returns the repo root Path. `project8_dir` names the subdirectory
    that stands in for project-8-your-own-daily-loop/.
    """

    def _make(project8_dir_name: str = "project-8-your-own-daily-loop", with_missing_project: bool = True):
        repo = tmp_path / "repo"
        repo.mkdir()
        _run(["git", "init", "-b", "main"], cwd=repo)
        _run(["git", "config", "user.email", "test@example.com"], cwd=repo)
        _run(["git", "config", "user.name", "Test"], cwd=repo)

        (repo / "README.md").write_text("# demo repo\n")

        p1 = repo / "project-1-alpha"
        p1.mkdir()
        (p1 / "README.md").write_text("# Project 1: Alpha\n\nFirst project.\n")

        if with_missing_project:
            p2 = repo / "project-2-beta"
            p2.mkdir()
            (p2 / "README.md").write_text("# Project 2: Beta\n\nSecond project.\n")

        p8 = repo / project8_dir_name
        p8.mkdir()
        (p8 / "README.md").write_text(f"# {project8_dir_name}\n")
        (p8 / "state").mkdir()

        _run(["git", "add", "-A"], cwd=repo)
        _run(["git", "commit", "-m", "initial commit"], cwd=repo)

        origin = tmp_path / "origin.git"
        _run(["git", "init", "--bare", str(origin)], cwd=tmp_path)
        _run(["git", "remote", "add", "origin", str(origin)], cwd=repo)
        _run(["git", "push", "-u", "origin", "main"], cwd=repo)

        return repo

    return _make


@pytest.fixture
def loop_env(monkeypatch, repo_factory):
    """A repo + a monkeypatched spine module pointed at it. Returns
    (repo_root, project8_dir, spine_module) for the test to use.
    """
    import spine as spine_mod

    repo = repo_factory()
    project8_dir = repo / "project-8-your-own-daily-loop"
    state_dir = project8_dir / "state"

    monkeypatch.setattr(spine_mod, "PROJECT8_DIR", project8_dir)
    monkeypatch.setattr(spine_mod, "STATE_DIR", state_dir)
    monkeypatch.setattr(spine_mod, "SPINE_PATH", state_dir / "spine.json")
    monkeypatch.setattr(spine_mod, "LEDGER_PATH", state_dir / "ledger.jsonl")
    monkeypatch.setattr(spine_mod, "LOG_PATH", state_dir / "run.log")
    monkeypatch.setattr(spine_mod, "STOP_PATH", state_dir / "STOP")
    monkeypatch.setattr(spine_mod, "LOCK_PATH", state_dir / "loop.lock")

    return repo, project8_dir, spine_mod
