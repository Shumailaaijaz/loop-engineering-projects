"""Checker (independent reviewer) for the root-README-index chore.

Follows the Project 4/5 convention exactly: this module is always
invoked with the *original* checkout's copy of itself, never the
candidate worktree's copy, so a candidate cannot influence how it is
graded even if its own copy of scripts/checker.py were touched. It
never takes the Maker's own report ("changed": true, "missing": [...])
as evidence -- every check below re-derives the answer independently
from the diff and the worktree's actual file contents.

Verdict is PASS only if every check passes. FAIL always comes with
concrete, specific reasons -- never a bare "looks wrong".
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import maker  # noqa: E402
from budget import BUDGET  # noqa: E402

LINK_RE = re.compile(r"\]\(([^)]+)\)")
FALLBACK_PYTEST_PYTHON = Path.home() / ".cache" / "loop-engineering-p5-pytest-venv" / "bin" / "python"
MISSING_PYTEST_MARKERS = ("No module named pytest", "No module named 'pytest'")
# This chore only ever touches the root README.md, so the regression sweep
# is a safety net over the *other* projects, not this loop's own code --
# re-running Project 8's own ~30 tests every single day would turn a
# deliberately cheap, fast chore into a slow one for no safety benefit.
# Project 8's own tests are validated separately (see README.md "Tests").
EXCLUDED_FROM_SWEEP = "project-8-your-own-daily-loop"


@dataclass
class CheckResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    tests: list[dict] = field(default_factory=list)
    files_changed: list[str] = field(default_factory=list)
    lines_changed: int = 0
    warnings: list[str] = field(default_factory=list)


def _run(cmd, cwd=None, env=None, timeout=60):
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)


def _git(repo_root: Path, *args, timeout=30):
    return _run(["git", "-C", str(repo_root), *args], timeout=timeout)


def get_changed_files(repo_root: Path, base_sha: str, head_sha: str) -> tuple[list[str] | None, str | None]:
    result = _git(repo_root, "diff", "--name-only", f"{base_sha}...{head_sha}")
    if result.returncode != 0:
        return None, result.stderr.strip()
    return [f for f in result.stdout.splitlines() if f.strip()], None


def get_lines_changed(repo_root: Path, base_sha: str, head_sha: str) -> tuple[int | None, str | None]:
    result = _git(repo_root, "diff", "--numstat", f"{base_sha}...{head_sha}")
    if result.returncode != 0:
        return None, result.stderr.strip()
    total = 0
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            total += int(parts[0]) + int(parts[1])
    return total, None


def verify_scope(changed_files: list[str]) -> list[str]:
    reasons = []
    if not changed_files:
        reasons.append("No changes were made -- nothing to review.")
        return reasons
    out_of_scope = [f for f in changed_files if f != "README.md"]
    if out_of_scope:
        reasons.append(
            "Change touches files outside the allowed scope ('README.md' only): "
            + ", ".join(out_of_scope)
        )
    return reasons


def verify_no_deletions(base_text: str, candidate_text: str) -> list[str]:
    base_lines = {line for line in base_text.splitlines() if line.strip()}
    candidate_lines = set(candidate_text.splitlines())
    missing = base_lines - candidate_lines
    if missing:
        preview = "\n".join(f"    - {line!r}" for line in sorted(missing)[:10])
        return [
            f"{len(missing)} line(s) present in the base README.md are no longer "
            f"present in the candidate (the Maker must only add lines, never "
            f"remove or edit existing ones):\n{preview}"
        ]
    return []


def verify_content(worktree_root: Path) -> list[str]:
    still_missing = maker.missing_projects(worktree_root)
    if still_missing:
        names = ", ".join(e.name for e in still_missing)
        return [f"Candidate README.md still does not reference: {names}"]
    return []


def verify_links(worktree_root: Path, candidate_text: str) -> list[str]:
    reasons = []
    for target in LINK_RE.findall(candidate_text):
        if target.startswith(("http://", "https://", "#")):
            continue
        if not (worktree_root / target).exists():
            reasons.append(f"README.md links to '{target}', which does not exist in the candidate.")
    return reasons


def verify_budget(files_changed: list[str], lines_changed: int) -> list[str]:
    reasons = []
    if len(files_changed) > BUDGET.max_files_changed:
        reasons.append(
            f"{len(files_changed)} file(s) changed, exceeds budget of {BUDGET.max_files_changed}."
        )
    if lines_changed > BUDGET.max_lines_changed:
        reasons.append(
            f"{lines_changed} line(s) changed, exceeds budget of {BUDGET.max_lines_changed}."
        )
    return reasons


def _resolve_pytest_python(project_dir: Path) -> str:
    override = os.environ.get("PYTEST_PYTHON")
    if override:
        return override
    local_venv = project_dir / ".venv" / "bin" / "python"
    if local_venv.exists():
        return str(local_venv)
    if FALLBACK_PYTEST_PYTHON.exists():
        return str(FALLBACK_PYTEST_PYTHON)
    return sys.executable


def discover_test_files(repo_root: Path) -> list[Path]:
    skip_dirs = {
        ".venv", ".worktrees", "__pycache__", ".git", "node_modules",
        ".pytest_cache", EXCLUDED_FROM_SWEEP,
    }
    found = []
    for path in repo_root.rglob("test_*.py"):
        if any(part in skip_dirs for part in path.parts):
            continue
        found.append(path)
    return sorted(found)


def _project_root_for(repo_root: Path, test_file: Path) -> Path:
    for parent in test_file.parents:
        if parent == repo_root:
            return repo_root
        if maker.PROJECT_DIR_RE.match(parent.name) and parent.parent == repo_root:
            return parent
    return repo_root


def run_test_sweep(repo_root: Path, timeout: int) -> list[dict]:
    results = []
    for test_file in discover_test_files(repo_root):
        project_dir = _project_root_for(repo_root, test_file)
        python_exe = _resolve_pytest_python(project_dir)
        env = os.environ.copy()
        # Different projects in this repo use different import styles
        # (project-6's tests do `from app import discount`, needing the
        # project root on the path; project-4's oracle test does bare
        # `from inventory import ...`, needing project_dir/app itself on
        # the path) -- cover both rather than guessing per-project.
        path_candidates = [project_dir, test_file.parent, project_dir / "app"]
        pythonpath = os.pathsep.join(
            dict.fromkeys(str(p) for p in path_candidates if p.is_dir())
        )
        env["PYTHONPATH"] = pythonpath
        rel = test_file.relative_to(repo_root)
        try:
            proc = _run(
                [python_exe, "-m", "pytest", "-q", str(test_file)],
                cwd=str(project_dir),
                env=env,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            results.append({"file": str(rel), "status": "FAIL", "detail": "pytest timed out"})
            continue
        output = proc.stdout + proc.stderr
        if proc.returncode == 0:
            status = "PASS"
        elif any(marker in output for marker in MISSING_PYTEST_MARKERS):
            status = "SKIPPED"
        else:
            status = "FAIL"
        results.append({"file": str(rel), "status": status, "detail": output.strip()[-500:]})
    return results


def review(worktree_root: Path, repo_root: Path, base_sha: str, head_sha: str, test_timeout: int = 90) -> CheckResult:
    reasons: list[str] = []

    changed_files, err = get_changed_files(repo_root, base_sha, head_sha)
    if err is not None:
        return CheckResult(passed=False, reasons=[f"Could not compute diff: {err}"])
    changed_files = changed_files or []

    lines_changed, err = get_lines_changed(repo_root, base_sha, head_sha)
    if err is not None:
        return CheckResult(passed=False, reasons=[f"Could not compute lines changed: {err}"])
    lines_changed = lines_changed or 0

    reasons += verify_scope(changed_files)
    reasons += verify_budget(changed_files, lines_changed)

    if "README.md" in changed_files:
        base_readme = _git(repo_root, "show", f"{base_sha}:README.md")
        base_text = base_readme.stdout if base_readme.returncode == 0 else ""
        candidate_text = (worktree_root / "README.md").read_text(errors="replace")

        reasons += verify_no_deletions(base_text, candidate_text)
        reasons += verify_content(worktree_root)
        reasons += verify_links(worktree_root, candidate_text)

    # A failure is only attributable to *this* candidate if the candidate
    # touched something other than README.md -- and verify_scope above
    # already turns any such touch into a blocking reason on its own. So
    # once we know the diff is README.md-only, any failing test here is
    # provably pre-existing (the code it exercises is byte-identical to
    # `base_sha`) -- worth surfacing loudly, but not this chore's fault to
    # block on. A future chore with real code scope would not get this
    # leniency: docs_only is only true when verify_scope found nothing to
    # object to.
    docs_only = changed_files == ["README.md"]

    warnings: list[str] = []
    test_results = run_test_sweep(repo_root, timeout=test_timeout)
    for t in test_results:
        if t["status"] != "FAIL":
            continue
        note = f"{t['file']} FAILED.\n    {t['detail']}"
        if docs_only:
            warnings.append(
                f"Pre-existing failure, unrelated to this README-only change: {note}"
            )
        else:
            reasons.append(f"Regression: {note}")

    return CheckResult(
        passed=(len(reasons) == 0),
        reasons=reasons,
        tests=test_results,
        files_changed=changed_files,
        lines_changed=lines_changed,
        warnings=warnings,
    )
