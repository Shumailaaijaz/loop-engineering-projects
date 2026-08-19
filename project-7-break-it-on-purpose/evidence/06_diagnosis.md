# Diagnosis — from the spine alone

Rule for this step: read only the last line of `brief.log` and the last
entry of `progress.md`. No re-running the script, no reading source, no
replaying the session.

## What `brief.log` (tail) says

```
[MORNING-BRIEF] FAILED 2026-08-20 01:25 PKT -- FileNotFoundError: BRIEF_WATCH_DIR does not exist: /mnt/d/Loop-Engineering-Projects/project-7-break-it-on-purpose/does-not-exist -- NEEDS HUMAN
```

## What `progress.md` (last entry) says

```
## 2026-08-20 01:25 PKT

RUN FAILED -- needs a human.

- watch dir: /mnt/d/Loop-Engineering-Projects/project-7-break-it-on-purpose/does-not-exist
- error: FileNotFoundError: BRIEF_WATCH_DIR does not exist: /mnt/d/Loop-Engineering-Projects/project-7-break-it-on-purpose/does-not-exist
- state was NOT updated this run (nothing new was marked seen)
```

## Diagnosis

- **What failed:** the beat's watch target (`BRIEF_WATCH_DIR`) pointed at
  a directory that does not exist on disk.
- **When:** 2026-08-20 01:25 PKT — the timestamp is on both lines, so no
  guessing from file mtimes is needed.
- **Blast radius:** none beyond this one beat. `state was NOT updated
  this run` in the spine entry confirms `seen_commits`/`seen_todos` were
  left exactly as the last good run left them — nothing was marked seen
  that wasn't actually checked, so tomorrow's run (once the path is
  fixed) will still report anything that was missed today.
- **Action required:** a human needs to fix `BRIEF_WATCH_DIR` (typo'd
  path, deleted directory, or a bad cron/env edit) and re-run. Nothing
  else in the loop needs touching — the failure is isolated to the one
  input path.

Both artifacts agree, are timestamped, name the exact broken input, and
say plainly that a human is needed — which is the whole point: neither
file required opening the script or replaying the run to answer "what
failed and when."
