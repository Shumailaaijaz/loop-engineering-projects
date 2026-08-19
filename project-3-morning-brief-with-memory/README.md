# Morning Brief with Memory

A tiny, unattended "morning brief" loop for this repository. Each run:

1. Reads `progress.md` (its persistent memory).
2. Gathers simple facts about the repo — Git commits from the last 24
   hours, and `TODO` comments found in tracked source files.
3. Compares those facts against what `progress.md` already recorded.
4. Prints a short human-readable brief containing **only the new
   findings**.
5. Appends the new findings (and the date) to `progress.md`, without
   touching or duplicating anything recorded on previous runs.

No AI API, database, or web app involved — it's a single Python
script plus a Markdown memory file.

## Files

- `scripts/morning_brief.py` — the core script. Reads/updates
  `progress.md`, does the comparison, prints the brief.
- `scripts/run_brief.sh` — thin wrapper that calls the script with the
  right interpreter/paths and appends output to `brief.log`. Intended
  for cron; also runnable by hand.
- `progress.md` — persistent memory. Contains a small JSON "state"
  block (which commit hashes / TODO signatures have already been
  reported) followed by a human-readable, append-only log of past
  briefs.
- `src/example.py` — a sample file with one `TODO` comment, included
  so there's something real for the script to discover on the first
  run.

## How the memory works

`progress.md` has two parts:

1. An HTML-comment JSON block (`<!--STATE ... STATE-->`) storing
   `seen_commits` (a list of full commit hashes) and `seen_todos` (a
   list of short hashes identifying `file:line:text`). This is the
   ground truth the script uses to decide what's "new."
2. A human-readable log below it — one `##` entry per run, each with
   a timestamp and the findings from that run only.

On every run the script:

- Loads `seen_commits` / `seen_todos` from the state block (an empty
  or missing `progress.md` is treated as "nothing seen yet" — no
  error).
- Collects the repo's *current* commits (last 24h) and *current*
  TODO comments.
- Subtracts the "seen" sets from the "current" sets → only genuinely
  new items remain.
- Prints those new items as the brief.
- Unions the new items into the seen sets and appends a dated entry
  to the log — it never rewrites or removes earlier entries, and
  never re-reports something already in `seen_commits` /
  `seen_todos`.

This is a real diff against prior state, not a re-dump of the whole
repo — if nothing changed since the last run, the brief says so
("No new commits...", "No new TODO comments...") instead of repeating
old findings.

## Running it

Run once, manually, from anywhere:

```bash
python3 scripts/morning_brief.py
```

Or via the wrapper (also appends to `brief.log`, used by cron):

```bash
bash scripts/run_brief.sh
```

## Scheduling in WSL (optional)

The script has no dependency on cron — it's just as valid to run it
by hand. If you do want it unattended, WSL ships with `cron`:

```bash
# start cron for this WSL session (if not already running)
sudo service cron start

# edit your crontab
crontab -e
```

Add a line to run it every morning at 7am:

```
0 7 * * * /usr/bin/bash /mnt/d/Loop-Engineering-Projects/project-3-morning-brief-with-memory/scripts/run_brief.sh
```

Output accumulates in `brief.log`; `progress.md` still holds the
authoritative, deduplicated memory.

## Demonstration: two consecutive runs proving memory

This is the exact sequence that was run to prove the memory behavior
(see `progress.md` in this repo for the real output).

### Run 1

```bash
$ python3 scripts/morning_brief.py
```

Actual output:

```
Morning Brief — 2026-08-18 23:03 PKT
First run: recording initial repository snapshot.
- 1 new commit(s) in the last 24h:
    - f7b557a Initial commit: morning brief with memory project
- 1 new TODO comment(s):
    - src/example.py:5: # TODO: validate that name is non-empty before greeting
```

`progress.md` after run 1 (trimmed to the log section):

```
## 2026-08-18 23:03 PKT

First run: recording initial repository snapshot.

- 1 new commit(s) in the last 24h:
    - f7b557a Initial commit: morning brief with memory project
- 1 new TODO comment(s):
    - src/example.py:5: # TODO: validate that name is non-empty before greeting
```

### One new repository change

A second `TODO` was added to `src/example.py` and committed:

```bash
$ git add src/example.py
$ git commit -m "Add input-length TODO to example"
```

### Run 2

```bash
$ python3 scripts/morning_brief.py
```

Actual output:

```
Morning Brief — 2026-08-18 23:03 PKT
Building on previous progress (see earlier entries below).
- 1 new commit(s) in the last 24h:
    - 5ffc9b6 Add input-length TODO to example
- 1 new TODO comment(s):
    - src/example.py:6: # TODO: reject names longer than 100 characters
```

Notice:

- It explicitly says *"Building on previous progress"* instead of
  "First run."
- It does **not** re-list the initial commit or the first TODO — both
  are already in `progress.md`'s state block, so they're filtered
  out.
- It reports only the one new commit and the one new TODO.

`progress.md` after run 2 — the run-1 entry is still there, untouched,
with a new entry appended below it:

```
## 2026-08-18 23:03 PKT

First run: recording initial repository snapshot.

- 1 new commit(s) in the last 24h:
    - f7b557a Initial commit: morning brief with memory project
- 1 new TODO comment(s):
    - src/example.py:5: # TODO: validate that name is non-empty before greeting

## 2026-08-18 23:03 PKT

Building on previous progress (see earlier entries below).

- 1 new commit(s) in the last 24h:
    - 5ffc9b6 Add input-length TODO to example
- 1 new TODO comment(s):
    - src/example.py:6: # TODO: reject names longer than 100 characters
```

Running the script a third time with no repository changes confirms
it stays quiet instead of re-reporting anything:

```
Morning Brief — 2026-08-18 23:04 PKT
Building on previous progress (see earlier entries below).
- No new commits in the last 24h.
- No new TODO comments.
```

## Limitations

- "Commits from the last 24h" is wall-clock based (`git log
  --since=24.hours`); if the script isn't run for more than a day,
  commits older than 24h at run time won't be picked up by that
  window — though already-seen commits are tracked forever via the
  state block regardless, so nothing already reported is ever lost or
  repeated, only "older than 24h and never previously seen" commits
  could be missed. Running at least daily avoids this entirely.
- TODO detection is a plain substring match for `TODO`; it doesn't
  understand comment syntax per language, so it can pick up `TODO`
  inside strings or docs, too — acceptable for an educational project
  like this one.
- Memory is a single local file (`progress.md`). It's not safe for
  concurrent runs (two `morning_brief.py` processes writing at once)
  — fine for a daily cron job, not for high-frequency or parallel
  scheduling.
- No AI/API summarization — the "brief" is a straightforward listing
  of new commits/TODOs, by design (project requirement: no external
  API, keep it simple).
