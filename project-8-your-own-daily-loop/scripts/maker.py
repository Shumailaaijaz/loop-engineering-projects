"""Maker for the "root README project index" chore.

The chore: the monorepo root README.md should list every `project-N-*`
directory that exists on disk. It currently does not (verified during
Project 8's own inspection: root README.md is a single line). New
project directories get added over time and the index goes stale again
-- this is a genuine, recurring, low-risk documentation-freshness chore.

This Maker is deliberately a plain deterministic script, not an LLM
call -- same reasoning Project 7 landed on for morning_brief.py: the
task is mechanical (list a directory, check for a substring, insert
lines), so a script does it for $0/month with no flakiness and no
prompt-injection surface from repository content. An optional
LLM-backed Maker (MAKER_CLI=claude, mirroring Project 5's swappable
knob) is documented in README.md for anyone who wants prose-drafted
entries instead; this module is the default path exercised by the loop
and by the tests.

Scope, enforced by construction (not just convention):
- Reads: every `project-*` directory name, each project's own
  README.md (first heading only).
- Writes: exactly one file, README.md, at the repo root -- and only
  ever *appends* new bullet lines, never edits or removes an existing
  line. The Checker independently re-verifies both of these.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

PROJECT_DIR_RE = re.compile(r"^project-(\d+)-")
PROJECTS_HEADING = "## Projects"


@dataclass(frozen=True)
class ProjectEntry:
    name: str
    number: int
    description: str
    has_readme: bool


def discover_project_dirs(repo_root: Path) -> list[Path]:
    dirs = []
    for child in repo_root.iterdir():
        if not child.is_dir():
            continue
        if child.name.startswith("."):
            continue
        if PROJECT_DIR_RE.match(child.name):
            dirs.append(child)
    return sorted(dirs, key=lambda d: int(PROJECT_DIR_RE.match(d.name).group(1)))


def _first_heading(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return None


def describe_project(project_dir: Path) -> ProjectEntry:
    match = PROJECT_DIR_RE.match(project_dir.name)
    number = int(match.group(1)) if match else -1
    readme = project_dir / "README.md"
    description = "(no project README found)"
    has_readme = readme.exists()
    if has_readme:
        try:
            text = readme.read_text(errors="replace")
        except OSError:
            text = ""
        heading = _first_heading(text)
        if heading:
            # Strip a redundant "Project N: " / "Project N — " prefix so
            # the index isn't "Project 4: Project 4 - Real bug...".
            heading = re.sub(r"^Project\s*\d+\s*[:—-]\s*", "", heading, flags=re.IGNORECASE)
            description = heading
    return ProjectEntry(
        name=project_dir.name, number=number, description=description, has_readme=has_readme
    )


def referenced_project_names(readme_text: str, project_dirs: list[Path]) -> set[str]:
    return {d.name for d in project_dirs if d.name in readme_text}


def missing_projects(repo_root: Path) -> list[ProjectEntry]:
    readme_path = repo_root / "README.md"
    readme_text = readme_path.read_text(errors="replace") if readme_path.exists() else ""
    project_dirs = discover_project_dirs(repo_root)
    referenced = referenced_project_names(readme_text, project_dirs)
    missing_dirs = [d for d in project_dirs if d.name not in referenced]
    return [describe_project(d) for d in missing_dirs]


def _entry_line(entry: ProjectEntry) -> str:
    if entry.has_readme:
        return f"- [{entry.name}]({entry.name}/README.md) — {entry.description}"
    return f"- {entry.name} — {entry.description}"


def build_patched_readme(readme_text: str, missing: list[ProjectEntry]) -> str:
    """Return new README text with `missing` entries inserted.

    Every existing line is preserved byte-for-byte, in its original
    order. New lines are inserted at the end of the "## Projects"
    section (creating that section at end-of-file if it doesn't exist
    yet) -- never anywhere else in the file.
    """
    new_lines = [_entry_line(e) for e in missing]
    if not new_lines:
        return readme_text

    lines = readme_text.splitlines()
    heading_idx = next(
        (i for i, line in enumerate(lines) if line.strip() == PROJECTS_HEADING), None
    )

    if heading_idx is None:
        prefix = readme_text
        if prefix and not prefix.endswith("\n"):
            prefix += "\n"
        if prefix and not prefix.endswith("\n\n"):
            prefix += "\n"
        body = prefix + PROJECTS_HEADING + "\n\n" + "\n".join(new_lines) + "\n"
        return body

    # Section end = next "## " heading after heading_idx, or EOF.
    section_end = len(lines)
    for i in range(heading_idx + 1, len(lines)):
        if lines[i].startswith("## "):
            section_end = i
            break

    # Trim trailing blank lines inside the section so insertion doesn't
    # accumulate blank lines run after run.
    insert_at = section_end
    while insert_at > heading_idx + 1 and lines[insert_at - 1].strip() == "":
        insert_at -= 1

    patched = lines[:insert_at] + new_lines + lines[insert_at:]
    text = "\n".join(patched)
    if readme_text.endswith("\n"):
        text += "\n"
    return text


def apply(worktree_root: Path) -> dict:
    """Run the Maker against a worktree checkout. Returns a result dict.

    Idempotent and safe to call on a worktree with no drift: returns
    changed=False and touches nothing.
    """
    readme_path = worktree_root / "README.md"
    readme_text = readme_path.read_text(errors="replace") if readme_path.exists() else ""
    missing = missing_projects(worktree_root)
    if not missing:
        return {"changed": False, "missing": [], "added_lines": []}

    patched = build_patched_readme(readme_text, missing)
    readme_path.write_text(patched)
    return {
        "changed": True,
        "missing": [e.name for e in missing],
        "added_lines": [_entry_line(e) for e in missing],
    }
