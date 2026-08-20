"""Spine: persistent memory for the Project 8 daily loop.

Mirrors the Project 3 / Project 7 pattern (progress.md: a small state
block plus an append-only human log) but split into three files, one per
concern:

- state/spine.json   -- machine state read/written every run (failure
                         streak, run counts, last status). This is what
                         makes run N+1 aware of run N.
- state/ledger.jsonl  -- one structured JSON object per run, append-only.
                         This is the audit trail ("what did the loop do
                         last night") -- see README.md Observability.
- state/run.log       -- human-readable, append-only, same events as the
                         ledger but skimmable in a terminal.

None of these three files are committed to git automatically by the loop
-- exactly like brief.log/progress.md in Projects 3 and 7, they live in
the working tree and are committed by a human at a checkpoint of their
choosing. Only the isolated worktree branch (the actual chore output) is
ever committed automatically. This keeps "the loop changes main's git
history on its own" from ever being true.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

PROJECT8_DIR = Path(__file__).resolve().parent.parent
STATE_DIR = PROJECT8_DIR / "state"
SPINE_PATH = STATE_DIR / "spine.json"
LEDGER_PATH = STATE_DIR / "ledger.jsonl"
LOG_PATH = STATE_DIR / "run.log"
STOP_PATH = STATE_DIR / "STOP"
LOCK_PATH = STATE_DIR / "loop.lock"

DEFAULT_SPINE = {
    "consecutive_failures": 0,
    "total_runs": 0,
    "last_run_utc": None,
    "last_status": None,
    "runs_today": {"date": None, "count": 0},
}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return _now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")


def today_str() -> str:
    return _now_utc().strftime("%Y-%m-%d")


def load_spine() -> dict:
    STATE_DIR.mkdir(exist_ok=True)
    if not SPINE_PATH.exists():
        return dict(DEFAULT_SPINE)
    try:
        data = json.loads(SPINE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        # Corrupt state file: treat as "nothing known" rather than crash
        # the loop. This is a deliberate fail-safe, not a silent hide --
        # the corruption itself is logged by the caller.
        return dict(DEFAULT_SPINE)
    merged = dict(DEFAULT_SPINE)
    merged.update(data)
    return merged


def save_spine(spine: dict) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    tmp = SPINE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(spine, indent=2, sort_keys=True) + "\n")
    tmp.replace(SPINE_PATH)  # atomic within the same filesystem


def runs_today(spine: dict) -> int:
    rt = spine.get("runs_today") or {}
    if rt.get("date") != today_str():
        return 0
    return int(rt.get("count", 0))


def record_run_started(spine: dict) -> dict:
    date = today_str()
    rt = spine.get("runs_today") or {}
    count = rt.get("count", 0) + 1 if rt.get("date") == date else 1
    spine["runs_today"] = {"date": date, "count": count}
    return spine


_HEALTHY_STATUSES = ("PUBLISHED", "NOOP")


def record_run_finished(spine: dict, status: str) -> dict:
    """Update the failure streak used by the circuit breaker.

    PUBLISHED/NOOP reset the streak -- the loop did its job (or found
    nothing to do), so it's proven itself healthy. Everything else
    (FAIL, ERROR, BUDGET_EXCEEDED, CONNECTOR_FAILED, and any future
    status this function doesn't yet know about) increments it: fail
    closed by default rather than silently treating an unrecognized
    status as fine.
    """
    spine["total_runs"] = int(spine.get("total_runs", 0)) + 1
    spine["last_run_utc"] = now_iso()
    spine["last_status"] = status
    if status in _HEALTHY_STATUSES:
        spine["consecutive_failures"] = 0
    else:
        spine["consecutive_failures"] = int(spine.get("consecutive_failures", 0)) + 1
    return spine


def append_ledger(entry: dict) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    with LEDGER_PATH.open("a") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def log(message: str) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    line = f"[{now_iso()}] {message}"
    print(line)
    with LOG_PATH.open("a") as f:
        f.write(line + "\n")


def is_stopped() -> tuple[bool, str | None]:
    if STOP_PATH.exists():
        try:
            return True, STOP_PATH.read_text().strip()
        except OSError:
            return True, "(STOP file present, reason unreadable)"
    return False, None


def write_stop(reason: str) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    STOP_PATH.write_text(
        f"{now_iso()} -- loop stopped itself: {reason}\n"
        "Delete this file to resume unattended runs after investigating.\n"
    )


def acquire_lock() -> bool:
    """Best-effort duplicate-execution guard via an exclusive-create lockfile.

    Returns True if the lock was acquired. A stale lock (older than 15
    minutes -- well beyond the runtime budget) is treated as abandoned
    and reclaimed rather than blocking forever.
    """
    STATE_DIR.mkdir(exist_ok=True)
    if LOCK_PATH.exists():
        try:
            age = _now_utc().timestamp() - LOCK_PATH.stat().st_mtime
        except OSError:
            age = 0
        if age < 15 * 60:
            return False
        # Stale lock: fall through and reclaim it.
    try:
        fd = os.open(str(LOCK_PATH), os.O_CREAT | os.O_WRONLY | os.O_TRUNC)
        os.write(fd, f"{os.getpid()} {now_iso()}\n".encode())
        os.close(fd)
        return True
    except OSError:
        return False


def release_lock() -> None:
    try:
        LOCK_PATH.unlink()
    except FileNotFoundError:
        pass
