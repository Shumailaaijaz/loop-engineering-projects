#!/usr/bin/env bash
DURATION="${1:-180}"   # seconds; default 3 min, override for testing e.g. ./long_task.sh 60
sleep "$DURATION"
echo "done at $(date -u +%FT%TZ)" > task.done.tmp
mv task.done.tmp task.done
