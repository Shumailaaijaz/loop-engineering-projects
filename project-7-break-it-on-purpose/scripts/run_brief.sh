#!/usr/bin/env bash
# Convenience wrapper so cron / manual runs always use the right
# interpreter and working directory regardless of caller's cwd.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

exec python3 "$SCRIPT_DIR/morning_brief.py" >> "$REPO_ROOT/brief.log" 2>&1
