#!/usr/bin/env python3
"""Reviewer / Checker for the Project 4 maker-checker demo.

Independently inspects a candidate fix living in a git worktree and
prints exactly PASS or FAIL (with concrete reasons). Never trusts the
implementer's own tests or claims as sufficient proof: it runs an
oracle test file the implementer does not control
(reviewer/oracle_tests/), and confirms that oracle actually detects the
original bug before trusting its verdict on the candidate.

Usage:
    python3 scripts/review_fix.py --worktree .worktrees/good-fix --base main

Exit code 0 on PASS, 1 on FAIL.
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ORACLE_DIR = PROJECT_ROOT / "reviewer" / "oracle_tests"
ALLOWED_SCOPE_PREFIX = "app/"


def _pytest_python():
    """Resolve a python interpreter that has pytest installed.

    Preference order: $PYTEST_PYTHON env var, this project's .venv,
    then whatever interpreter is running this script.
    """
    import os

    override = os.environ.get("PYTEST_PYTHON")
    if override:
        return override
    local_venv = PROJECT_ROOT / ".venv" / "bin" / "python"
    if local_venv.exists():
        return str(local_venv)
    return sys.executable


def run(cmd, cwd=None, env=None):
    return subprocess.run(
        cmd, cwd=cwd, env=env, capture_output=True, text=True
    )


def git(worktree, *args):
    return run(["git", "-C", str(worktree), *args])


def get_changed_files(worktree, base):
    # --relative makes paths relative to `worktree` (the project subdir)
    # rather than the repo root, so this also works when the project
    # lives inside a larger monorepo checkout.
    result = git(worktree, "diff", "--name-only", "--relative", f"{base}...HEAD")
    if result.returncode != 0:
        return None, result.stderr.strip()
    files = [f for f in result.stdout.splitlines() if f.strip()]
    return files, None


def run_pytest(target, pythonpath, extra_env=None):
    import os

    env = os.environ.copy()
    env["PYTHONPATH"] = str(pythonpath)
    if extra_env:
        env.update(extra_env)
    result = run([_pytest_python(), "-m", "pytest", "-q", str(target)], env=env)
    return result


def check_oracle_detects_bug_on_baseline(worktree, base):
    """Sanity-check: the oracle must FAIL against the pre-fix baseline.

    This proves the oracle test is actually capable of detecting the
    reported bug, rather than trivially passing on anything.
    """
    # The leading "./" makes the path resolve relative to `worktree`
    # (the -C cwd) instead of the repo root.
    show = git(worktree, "show", f"{base}:./app/inventory.py")
    if show.returncode != 0:
        return False, f"could not read {base}:./app/inventory.py ({show.stderr.strip()})"

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "inventory.py").write_text(show.stdout)
        result = run_pytest(ORACLE_DIR, tmp_path)
        baseline_fails = result.returncode != 0
        return baseline_fails, result.stdout + result.stderr


def review(worktree, base):
    reasons = []
    worktree = Path(worktree).resolve()

    is_worktree = git(worktree, "rev-parse", "--is-inside-work-tree")
    if is_worktree.returncode != 0 or is_worktree.stdout.strip() != "true":
        return False, [f"{worktree} is not inside a git worktree."]

    inventory_path = worktree / "app" / "inventory.py"
    if not inventory_path.exists():
        return False, [f"{inventory_path} does not exist in the candidate worktree."]

    # --- Scope check -------------------------------------------------
    changed_files, err = get_changed_files(worktree, base)
    if err is not None:
        return False, [f"Could not compute diff against {base}: {err}"]
    if not changed_files:
        reasons.append(
            f"No changes detected between {base} and the candidate branch — "
            "no fix was made."
        )
    else:
        out_of_scope = [f for f in changed_files if not f.startswith(ALLOWED_SCOPE_PREFIX)]
        if out_of_scope:
            reasons.append(
                "Change touches files outside the allowed scope "
                f"('{ALLOWED_SCOPE_PREFIX}*'): " + ", ".join(out_of_scope)
            )

    # --- Oracle sanity check on baseline ------------------------------
    baseline_fails, baseline_output = check_oracle_detects_bug_on_baseline(worktree, base)
    if not baseline_fails:
        reasons.append(
            "Oracle sanity check failed: the independent oracle test in "
            "reviewer/oracle_tests/ does NOT fail against the pre-fix "
            f"baseline ({base}). The oracle cannot be trusted to validate "
            "this fix until it correctly detects the original bug."
        )

    # --- Oracle test against candidate --------------------------------
    candidate_result = run_pytest(ORACLE_DIR, worktree / "app")
    if candidate_result.returncode != 0:
        reasons.append(
            "Independent oracle regression test "
            "(reviewer/oracle_tests/test_remove_duplicates_bug.py) FAILED "
            "against the candidate implementation. Output:\n"
            + indent(candidate_result.stdout + candidate_result.stderr)
        )

    # --- Full existing test suite (regression safety) ------------------
    suite_result = run(
        [_pytest_python(), "-m", "pytest", "-q", str(worktree / "app")]
    )
    if suite_result.returncode != 0:
        reasons.append(
            "The existing test suite in app/ has at least one failure on "
            "the candidate branch (regression). Output:\n"
            + indent(suite_result.stdout + suite_result.stderr)
        )

    passed = len(reasons) == 0
    return passed, reasons


def indent(text, prefix="    "):
    return "\n".join(prefix + line for line in text.splitlines())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worktree", required=True, help="Path to the candidate git worktree")
    parser.add_argument("--base", default="main", help="Base branch/ref to diff and compare against (default: main)")
    args = parser.parse_args()

    passed, reasons = review(args.worktree, args.base)

    if passed:
        print("PASS")
        sys.exit(0)
    else:
        print("FAIL")
        for reason in reasons:
            print(f"Reason: {reason}")
        sys.exit(1)


if __name__ == "__main__":
    main()
