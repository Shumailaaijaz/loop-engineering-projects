import maker


def _isolate_beta_as_the_only_gap(repo):
    """repo_factory() also creates the project-8-* dir itself (it has to,
    for spine paths to resolve in the shared fixtures used elsewhere), and
    that dir matches the same project-N-* pattern maker.py scans for. Pin
    the root README so project-1-alpha and the project-8 dir already count
    as referenced, leaving project-2-beta as the one deliberate gap these
    tests are about.
    """
    project8_name = next(p.name for p in repo.iterdir() if p.name.startswith("project-8-"))
    (repo / "README.md").write_text(f"# demo repo\n\nproject-1-alpha\n{project8_name}\n")
    return project8_name


def test_discover_project_dirs_sorted_by_number(repo_factory):
    repo = repo_factory()
    project8_name = next(p.name for p in repo.iterdir() if p.name.startswith("project-8-"))
    (repo / "project-10-late").mkdir()
    (repo / "not-a-project").mkdir()
    dirs = [d.name for d in maker.discover_project_dirs(repo)]
    assert dirs == ["project-1-alpha", "project-2-beta", project8_name, "project-10-late"]


def test_missing_projects_detects_undocumented_dir(repo_factory):
    repo = repo_factory()
    _isolate_beta_as_the_only_gap(repo)
    missing = maker.missing_projects(repo)
    names = [e.name for e in missing]
    assert names == ["project-2-beta"]
    assert missing[0].description == "Beta"
    assert missing[0].has_readme is True


def test_missing_projects_empty_when_all_referenced(repo_factory):
    repo = repo_factory()
    project8_name = _isolate_beta_as_the_only_gap(repo)
    (repo / "README.md").write_text(
        f"# demo repo\n\n## Projects\n\n- project-1-alpha\n- project-2-beta\n- {project8_name}\n"
    )
    assert maker.missing_projects(repo) == []


def test_build_patched_readme_preserves_existing_lines(repo_factory):
    repo = repo_factory()
    _isolate_beta_as_the_only_gap(repo)
    original = (repo / "README.md").read_text()
    missing = maker.missing_projects(repo)
    patched = maker.build_patched_readme(original, missing)
    for line in original.splitlines():
        assert line in patched.splitlines()


def test_build_patched_readme_creates_heading_if_absent(repo_factory):
    repo = repo_factory()
    _isolate_beta_as_the_only_gap(repo)
    original = (repo / "README.md").read_text()
    assert "## Projects" not in original
    missing = maker.missing_projects(repo)
    patched = maker.build_patched_readme(original, missing)
    assert "## Projects" in patched
    assert "- [project-2-beta](project-2-beta/README.md) — Beta" in patched


def test_build_patched_readme_inserts_under_existing_heading_without_disturbing_it(repo_factory):
    repo = repo_factory()
    project8_name = _isolate_beta_as_the_only_gap(repo)
    (repo / "README.md").write_text(
        f"# demo repo\n\n## Projects\n\n- project-1-alpha — Alpha\n- {project8_name}\n\n"
        "## Other Section\n\nkeep me\n"
    )
    missing = maker.missing_projects(repo)
    patched = maker.build_patched_readme((repo / "README.md").read_text(), missing)
    lines = patched.splitlines()
    assert "- project-1-alpha — Alpha" in lines
    assert "- [project-2-beta](project-2-beta/README.md) — Beta" in lines
    assert lines.index("- [project-2-beta](project-2-beta/README.md) — Beta") < lines.index("## Other Section")
    assert "keep me" in patched


def test_apply_is_noop_when_nothing_missing(repo_factory):
    repo = repo_factory(with_missing_project=False)
    project8_name = next(p.name for p in repo.iterdir() if p.name.startswith("project-8-"))
    (repo / "README.md").write_text(f"# demo repo\n\nproject-1-alpha\n{project8_name}\n")
    before = (repo / "README.md").read_text()
    result = maker.apply(repo)
    assert result == {"changed": False, "missing": [], "added_lines": []}
    assert (repo / "README.md").read_text() == before


def test_apply_writes_readme_when_missing(repo_factory):
    repo = repo_factory()
    _isolate_beta_as_the_only_gap(repo)
    result = maker.apply(repo)
    assert result["changed"] is True
    assert result["missing"] == ["project-2-beta"]
    text = (repo / "README.md").read_text()
    assert "project-2-beta" in text
    # idempotent: applying again is now a no-op
    second = maker.apply(repo)
    assert second["changed"] is False


def test_apply_only_touches_readme(repo_factory):
    repo = repo_factory()
    _isolate_beta_as_the_only_gap(repo)
    before = {
        p: p.read_bytes()
        for p in repo.rglob("*")
        if p.is_file() and p.name != "README.md" and ".git" not in p.parts
    }
    maker.apply(repo)
    after = {p: p.read_bytes() for p in before}
    assert before == after
