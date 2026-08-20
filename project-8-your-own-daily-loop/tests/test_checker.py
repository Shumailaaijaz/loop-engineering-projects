import subprocess

import checker
import maker
from budget import Budget


def _git(cmd, cwd):
    result = subprocess.run(["git", "-C", str(cwd), *cmd], capture_output=True, text=True)
    assert result.returncode == 0, f"git {cmd} failed: {result.stderr}"
    return result


def _rev_parse(repo, ref="HEAD"):
    return _git(["rev-parse", ref], repo).stdout.strip()


def make_candidate(repo, mutate_fn, message="candidate change"):
    base_sha = _rev_parse(repo)
    worktree_path = repo.parent / "wt"
    _git(["worktree", "add", str(worktree_path), "-b", "candidate", base_sha], repo)
    mutate_fn(worktree_path)
    _git(["add", "-A"], worktree_path)
    commit = subprocess.run(
        ["git", "-C", str(worktree_path), "commit", "-m", message],
        capture_output=True, text=True,
    )
    head_sha = commit.stdout and _rev_parse(worktree_path) or base_sha
    return worktree_path, base_sha, head_sha


def test_review_passes_for_correct_maker_patch(repo_factory):
    repo = repo_factory()
    worktree_path, base_sha, head_sha = make_candidate(repo, lambda wt: maker.apply(wt))
    result = checker.review(worktree_path, repo, base_sha, head_sha)
    assert result.passed is True, result.reasons
    assert result.reasons == []
    assert result.files_changed == ["README.md"]


def test_review_fails_on_scope_violation(repo_factory):
    repo = repo_factory()

    def mutate(wt):
        maker.apply(wt)
        (wt / "project-1-alpha" / "README.md").write_text("# Project 1: Alpha\n\ntampered\n")

    worktree_path, base_sha, head_sha = make_candidate(repo, mutate)
    result = checker.review(worktree_path, repo, base_sha, head_sha)
    assert result.passed is False
    assert any("outside the allowed scope" in r for r in result.reasons)


def test_review_fails_on_no_changes(repo_factory):
    repo = repo_factory()
    worktree_path, base_sha, head_sha = make_candidate(repo, lambda wt: None)
    result = checker.review(worktree_path, repo, base_sha, head_sha)
    assert result.passed is False
    assert any("No changes were made" in r for r in result.reasons)


def test_review_fails_on_deleted_line(repo_factory):
    repo = repo_factory()

    def mutate(wt):
        maker.apply(wt)
        readme = wt / "README.md"
        # Drop the original heading line entirely.
        readme.write_text(readme.read_text().replace("# demo repo\n", ""))

    worktree_path, base_sha, head_sha = make_candidate(repo, mutate)
    result = checker.review(worktree_path, repo, base_sha, head_sha)
    assert result.passed is False
    assert any("no longer" in r for r in result.reasons)


def test_review_fails_when_project_still_missing(repo_factory):
    repo = repo_factory()

    def mutate(wt):
        (wt / "README.md").write_text((wt / "README.md").read_text() + "\nunrelated note\n")

    worktree_path, base_sha, head_sha = make_candidate(repo, mutate)
    result = checker.review(worktree_path, repo, base_sha, head_sha)
    assert result.passed is False
    assert any("project-2-beta" in r for r in result.reasons)


def test_review_fails_on_broken_link(repo_factory):
    repo = repo_factory()

    def mutate(wt):
        maker.apply(wt)
        readme = wt / "README.md"
        readme.write_text(readme.read_text() + "\n- [nowhere](does-not-exist/README.md)\n")

    worktree_path, base_sha, head_sha = make_candidate(repo, mutate)
    result = checker.review(worktree_path, repo, base_sha, head_sha)
    assert result.passed is False
    assert any("does not exist" in r for r in result.reasons)


def test_review_warns_but_does_not_block_on_preexisting_unrelated_failure(repo_factory):
    # A test failure elsewhere in the repo, unrelated to and unaffected by
    # a README-only change (the failing code is byte-identical to base),
    # is provably not this candidate's fault -- it should surface as a
    # warning, not block an otherwise-correct docs-only PASS.
    repo = repo_factory()
    broken = repo / "project-3-gamma"
    broken.mkdir()
    (broken / "test_broken.py").write_text("def test_always_fails():\n    assert False\n")
    _git(["add", "-A"], repo)
    _git(["commit", "-m", "add broken project"], repo)

    worktree_path, base_sha, head_sha = make_candidate(repo, lambda wt: maker.apply(wt))
    result = checker.review(worktree_path, repo, base_sha, head_sha)
    assert result.passed is True, result.reasons
    assert not any("Regression" in r for r in result.reasons)
    assert any("Pre-existing failure" in w for w in result.warnings)
    statuses = {t["file"]: t["status"] for t in result.tests}
    assert statuses.get("project-3-gamma/test_broken.py") == "FAIL"


def test_review_fails_on_regression_when_scope_is_not_docs_only(repo_factory):
    # Once a candidate touches anything beyond README.md, it no longer
    # gets the "provably unaffected" leniency above -- a test failure
    # blocks it (in addition to the scope violation itself).
    repo = repo_factory()
    broken = repo / "project-3-gamma"
    broken.mkdir()
    (broken / "test_broken.py").write_text("def test_always_fails():\n    assert False\n")
    _git(["add", "-A"], repo)
    _git(["commit", "-m", "add broken project"], repo)

    def mutate(wt):
        (wt / "project-1-alpha" / "README.md").write_text("# Project 1: Alpha\n\ntampered\n")

    worktree_path, base_sha, head_sha = make_candidate(repo, mutate)
    result = checker.review(worktree_path, repo, base_sha, head_sha)
    assert result.passed is False
    assert any("outside the allowed scope" in r for r in result.reasons)
    assert any("Regression" in r for r in result.reasons)


def test_review_respects_lines_changed_budget(monkeypatch, repo_factory):
    repo = repo_factory()
    monkeypatch.setattr(checker, "BUDGET", Budget(max_lines_changed=0))
    worktree_path, base_sha, head_sha = make_candidate(repo, lambda wt: maker.apply(wt))
    result = checker.review(worktree_path, repo, base_sha, head_sha)
    assert result.passed is False
    assert any("exceeds budget" in r for r in result.reasons)
