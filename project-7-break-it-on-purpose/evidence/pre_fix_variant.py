#!/usr/bin/env python3
"""
Morning Brief with Memory (Project 7: break-it-on-purpose variant)
--------------------------------------------------------------------
Same loop as Project 3: reads progress.md, scans a target repo for new
Git commits (last 24h) and new TODO comments, prints a short brief, and
appends only the *new* findings to progress.md.

Two changes from Project 3, both for this exercise:

1. The directory it watches is now configurable via BRIEF_WATCH_DIR
   (defaults to this repo), so it can be pointed at a bad path on
   purpose without editing the script.
2. main() no longer lets a failure pass silently. Any exception is
   caught, written as one greppable line to stdout/brief.log, and
   recorded as a dated "needs a human" entry in progress.md itself,
   so the spine always shows the last thing that happened -- success
   or failure -- without anyone needing to replay the run.

Usage:
    python3 scripts/morning_brief.py
    BRIEF_WATCH_DIR=/some/other/repo python3 scripts/morning_brief.py
"""

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROGRESS_FILE = REPO_ROOT / "progress.md"

# The repo/directory this beat watches for commits and TODOs. Defaults to
# this project, but is overridable -- e.g. to watch a different repo, or
# (for this exercise) to sabotage the loop by pointing it at a path that
# does not exist.
WATCH_DIR = Path(os.environ.get("BRIEF_WATCH_DIR", str(REPO_ROOT)))

STATE_START = "<!--STATE"
STATE_END = "STATE-->"

DEFAULT_STATE = {"seen_commits": [], "seen_todos": []}

TODO_PATTERN = re.compile(r"\bTODO\b(.*)")
IGNORED_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", "evidence"}

# Only scan actual source-code files for TODOs, so prose that merely
# *mentions* the word "TODO" (e.g. in this README) is never mistaken
# for a real TODO comment.
SOURCE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".c", ".h", ".cpp",
    ".hpp", ".go", ".rb", ".rs", ".sh", ".bash", ".php", ".cs", ".swift",
    ".kt", ".m", ".scala",
}


# ---------------------------------------------------------------------------
# progress.md <-> state helpers
# ---------------------------------------------------------------------------

def load_progress():
    """Return (state_dict, log_text). Handles missing/empty/corrupt file."""
    if not PROGRESS_FILE.exists() or PROGRESS_FILE.stat().st_size == 0:
        return dict(DEFAULT_STATE), ""

    text = PROGRESS_FILE.read_text(encoding="utf-8")

    start = text.find(STATE_START)
    end = text.find(STATE_END)
    if start == -1 or end == -1:
        # No recognizable state block yet -> treat everything as the log
        return dict(DEFAULT_STATE), text.strip()

    raw_json = text[start + len(STATE_START):end].strip()
    try:
        state = json.loads(raw_json)
    except json.JSONDecodeError:
        state = dict(DEFAULT_STATE)

    state.setdefault("seen_commits", [])
    state.setdefault("seen_todos", [])

    log_text = text[end + len(STATE_END):].strip()

    # The saved file always re-prepends a fixed header before the entries;
    # strip it back off here so it isn't duplicated on the next save. Only
    # the "## <date>" entries themselves are treated as persisted log
    # content.
    first_entry = log_text.find("## ")
    log_text = log_text[first_entry:].strip() if first_entry != -1 else ""

    return state, log_text


def save_progress(state, log_text):
    state_block = f"{STATE_START}\n{json.dumps(state, indent=2)}\n{STATE_END}"
    header = (
        "# Morning Brief Progress Log\n\n"
        "This file is the persistent memory for the morning-brief script.\n"
        "The JSON block above the log tracks which commits and TODOs have\n"
        "already been reported, so future runs only surface *new* items.\n"
        "Do not hand-edit the JSON block unless you know what you're doing.\n"
    )
    content = f"{state_block}\n\n{header}\n{log_text.strip()}\n"
    PROGRESS_FILE.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Gathering current repo info
# ---------------------------------------------------------------------------

def get_recent_commits(hours=24):
    """Return list of (hash, subject) for commits in the last `hours`."""
    try:
        result = subprocess.run(
            [
                "git", "log",
                f"--since={hours}.hours",
                "--pretty=format:%H|%s",
            ],
            cwd=WATCH_DIR,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []

    commits = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        commit_hash, _, subject = line.partition("|")
        commits.append((commit_hash, subject))
    return commits


def get_todo_comments():
    """Return list of (signature, file, line_no, text) for TODO comments."""
    todos = []
    for path in sorted(WATCH_DIR.rglob("*")):
        if not path.is_file():
            continue
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        if path.suffix not in SOURCE_EXTENSIONS:
            continue
        if path.resolve() == Path(__file__).resolve():
            continue  # don't flag TODO mentions inside this script itself
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except (UnicodeDecodeError, OSError):
            continue

        for line_no, line in enumerate(lines, start=1):
            if not TODO_PATTERN.search(line):
                continue
            rel_path = path.relative_to(WATCH_DIR)
            text = line.strip()
            signature_src = f"{rel_path}:{line_no}:{text}"
            signature = hashlib.sha1(signature_src.encode("utf-8")).hexdigest()[:12]
            todos.append((signature, str(rel_path), line_no, text))
    return todos


# ---------------------------------------------------------------------------
# Brief building
# ---------------------------------------------------------------------------

def build_brief(new_commits, new_todos):
    lines = []
    if new_commits:
        lines.append(f"- {len(new_commits)} new commit(s) in the last 24h:")
        for commit_hash, subject in new_commits:
            lines.append(f"    - {commit_hash[:7]} {subject}")
    else:
        lines.append("- No new commits in the last 24h.")

    if new_todos:
        lines.append(f"- {len(new_todos)} new TODO comment(s):")
        for _, rel_path, line_no, text in new_todos:
            lines.append(f"    - {rel_path}:{line_no}: {text}")
    else:
        lines.append("- No new TODO comments.")

    return "\n".join(lines)


def _run(date_str):
    # NOTE (Project 7 evidence): this is deliberately the PRE-FIX shape --
    # no check that WATCH_DIR exists. This is exactly what Project 3's
    # original code did (it never validated its target either).
    state, log_text = load_progress()
    is_first_run = not log_text.strip()

    seen_commit_hashes = set(state["seen_commits"])
    seen_todo_sigs = set(state["seen_todos"])

    all_commits = get_recent_commits()
    all_todos = get_todo_comments()

    new_commits = [c for c in all_commits if c[0] not in seen_commit_hashes]
    new_todos = [t for t in all_todos if t[0] not in seen_todo_sigs]

    brief_body = build_brief(new_commits, new_todos)

    if is_first_run:
        mode_line = "First run: recording initial repository snapshot."
    else:
        mode_line = "Building on previous progress (see earlier entries below)."

    brief = (
        f"Morning Brief — {date_str}\n"
        f"{mode_line}\n"
        f"{brief_body}\n"
    )

    print(brief)

    # Update state with everything we've now seen
    state["seen_commits"] = sorted(seen_commit_hashes | {c[0] for c in all_commits})
    state["seen_todos"] = sorted(seen_todo_sigs | {t[0] for t in all_todos})

    entry = f"## {date_str}\n\n{mode_line}\n\n{brief_body}\n"
    new_log_text = f"{log_text.strip()}\n\n{entry}".strip() if log_text.strip() else entry

    save_progress(state, new_log_text)


# NOTE (Project 7 evidence): no _record_failure, and main() below has no
# try/except -- exactly Project 3's original main(). Nothing here catches
# a failure, validates WATCH_DIR, writes a clear log line, or notes
# anything in progress.md. Kept only so the "silent failure" claim in the
# README is demonstrated, not just asserted -- scripts/morning_brief.py
# (the real, fixed script) is what actually runs from now on.


def main():
    now = datetime.now(timezone.utc).astimezone()
    date_str = now.strftime("%Y-%m-%d %H:%M %Z")
    _run(date_str)


if __name__ == "__main__":
    main()
