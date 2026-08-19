# Project 1: Watch Loop

**Concept:** In-session loop (Loop Engineering — Easy)

A long-running task writes a completion signal file when it finishes. A `/loop`-based
watch checks for that signal once a minute and reports completion exactly once,
without anyone needing to watch the terminal.

## Files

- `long_task.sh` — the long-running task. Sleeps for a configurable duration, then
  writes the completion signal.
- `task.done` — created by `long_task.sh` at runtime. Its existence means the task
  finished. Not committed to git (see `.gitignore`).
- `.gitignore` — excludes runtime-generated files (`task.done`, `task.done.tmp`) and
  OS clutter (`.DS_Store`, `Thumbs.db`).

## Running the task

```bash
./long_task.sh          # default: 180 seconds (3 minutes)
./long_task.sh 90 &     # override duration, run in background (e.g. for a quick test)
```

## How completion is signaled

`long_task.sh` writes its result to a temporary file first, then renames it into
place:

```bash
echo "done at $(date -u +%FT%TZ)" > task.done.tmp
mv task.done.tmp task.done
```

`mv` within the same filesystem is atomic, so `task.done` is never observed
half-written — it either doesn't exist yet, or exists complete.

## How the watch loop works

Started with `/loop 1m`, which schedules a recurring check every minute:

- If `task.done` does **not** exist: stay silent, check again next minute.
- If `task.done` **does** exist: read its timestamp, report completion exactly once,
  then stop the loop immediately (no further checks).

Because the loop stops itself in the same tick that reports completion, a duplicate
report is structurally impossible — there's no next tick to produce one.

## Done-when checklist

1. **Notices completion** — the loop detects `task.done` on its next 1-minute check
   after the file appears.
2. **Reports only once** — the loop stops itself immediately after reporting, so it
   cannot fire again.
3. **Stops cleanly** — the recurring check is cancelled (no leftover scheduled job);
   it can also be stopped manually before completion if needed.
4. **No continuous watching required** — the completion message arrives on its own;
   no need to poll or watch the terminal.
