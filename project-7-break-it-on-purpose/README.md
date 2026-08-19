# Project 7: Break It on Purpose

Takes the [Project 3](../project-3-morning-brief-with-memory) morning-brief
loop and rehearses its overnight failure on purpose, while it's cheap and
someone is watching, instead of finding out the hard way at 7am with
nobody around.

Three things had to end up true:

1. You can say **what failed and when**, from `brief.log` and `progress.md`
   alone — no replaying the run.
2. The loop leaves a clear **"needs a human"** note instead of failing
   silently.
3. You know the loop's **monthly cost** at its current cadence.

All three are demonstrated below with real command output, not narrated.

## The loop, unchanged in spirit

Same shape as Project 3: a cron-scheduled Python script
(`scripts/morning_brief.py` + `scripts/run_brief.sh`) that reads
`progress.md` (its spine), scans a repo for new commits and TODOs,
prints a brief, and appends only what's new. No AI/API calls — it's
still a plain script, which matters for the cost step below.

Two additions for this exercise, both in `scripts/morning_brief.py`:

- **`BRIEF_WATCH_DIR`** — the directory the beat watches is now an
  overridable env var (default: this project), so it can be pointed at
  a bad path without editing code. This is the knob the sabotage turns.
- **Failure handling in `main()`** — the fix described below.

## Step 1 — Concept 13: what does this loop cost per month?

The honest answer first: **$0.00/month, at any cadence.** This loop
makes zero model calls — it's deterministic Python reading files and
running `git log`. Concept 13's formula is `tokens/beat × price/token ×
beats/month`, and `tokens/beat` here is 0, so the product is 0 regardless
of how often it fires. Scheduled daily at 7am per Project 3's crontab
line (`0 7 * * *`, ~30 beats/month), the bill is the same $0 as scheduled
every five minutes. That's not a dodge — it's the real number, and it's
the reason this whole exercise is safe to rehearse on a live schedule
with zero risk of a surprise invoice.

**Illustrative only** (not what actually runs): if this same beat were
done by Claude instead of raw Python — reading `progress.md` plus a
short task prompt and writing the brief plus the updated spine — here's
what Concept 13's math would say, using Sonnet 5 pricing looked up live
via the `claude-api` skill (checked 2026-08-20):

| | Standard | Intro (through 2026-08-31) |
|---|---|---|
| Input | $3.00/MTok | $2.00/MTok |
| Output | $15.00/MTok | $10.00/MTok |

Measured inputs: `progress.md` is 1,635 bytes (~409 tokens at ~4
chars/token) after the baseline run below; a short task prompt/instructions
add roughly another ~900 tokens; call it **~1,300 input tokens/beat**.
Output — the brief plus the updated spine diff — is roughly **~600
tokens/beat**.

```
per beat (standard) = 1,300 × $3/1e6 + 600 × $15/1e6  ≈ $0.013
per beat (intro)     = 1,300 × $2/1e6 + 600 × $10/1e6  ≈ $0.009

× 30 beats/month (daily cadence):
  standard ≈ $0.39/month
  intro    ≈ $0.26/month
```

Even hypothetically AI-driven, this loop is cheap — its whole per-beat
payload is a couple thousand tokens, nowhere near Concept 13's own
worked example of a 40k-in/6k-out maker+checker beat (~$0.20/beat,
~$1,000+/month at 5-minute cadence). The lesson generalizes even to a
$0 loop: cost is `tokens/beat × frequency`, and frequency is the lever
that runs away on you, not the command name.

## Step 2 — the sabotage

Chose "point the prompt at a file that does not exist" over "success
condition it can never meet": this loop has no retry/success-condition
mechanism to sabotage (it's not a maker-checker loop), but it does have
exactly one external target — `BRIEF_WATCH_DIR` — that's a perfect fit
for "point it at something that isn't there."

**First surprise:** doing this against Project 3's original code doesn't
crash at all. `subprocess.run(cwd=<missing>)` is already caught and
returns `[]`; `Path.rglob()` on a missing directory silently yields
nothing on this Python version (3.12). The result is worse than a
crash — the script exits 0 and prints a perfectly normal-looking brief
("No new commits... No new TODO comments.") while actually watching
nothing. That's a **silent wrong success**, not a loud failure, and it's
exactly the failure mode Concept 14's "checking the work is still your
job" note warns about: "done" is a claim, not a proof.

`evidence/pre_fix_variant.py` is a byte-for-byte copy of the script
before the fix below — same `BRIEF_WATCH_DIR` feature, but none of the
failure handling. Running it against the sabotage proves the claim
instead of just asserting it:

```
$ BRIEF_WATCH_DIR=.../does-not-exist python3 evidence/pre_fix_variant.py
Morning Brief — 2026-08-20 01:25 PKT
Building on previous progress (see earlier entries below).
- No new commits in the last 24h.
- No new TODO comments.

exit code: 0
```
(full capture: `evidence/02_before_fix_run.txt`)

And `progress.md` picks up a new entry that is indistinguishable from a
real quiet day (`evidence/03_progress_after_silent_wrong_success.md`):

```
## 2026-08-20 01:25 PKT

Building on previous progress (see earlier entries below).

- No new commits in the last 24h.
- No new TODO comments.
```

Nothing in the spine hints anything is wrong. This is the silent failure
the task says to fix before anything else.

## Step 3 — the fix

Two changes in `scripts/morning_brief.py`:

1. **Validate the target up front.** `_run()` now raises immediately if
   `WATCH_DIR` isn't a real directory, converting the silent wrong
   success into a real, loud exception.
2. **Catch it and leave a spine note.** `main()` wraps the run in
   `try/except`. On failure it writes one greppable line to
   `brief.log` (`[MORNING-BRIEF] FAILED ... NEEDS HUMAN`) *and* appends
   a dated `RUN FAILED -- needs a human` entry directly into
   `progress.md`, then exits non-zero. `seen_commits`/`seen_todos` are
   left untouched, so nothing gets falsely marked "seen."

Running the real, fixed script through the actual production wrapper
(`run_brief.sh`) against the same sabotage:

```
$ BRIEF_WATCH_DIR=.../does-not-exist bash scripts/run_brief.sh
$ echo $?
1
```

`brief.log` tail (`evidence/04_sabotaged_run_brief_log.txt`):

```
[MORNING-BRIEF] FAILED 2026-08-20 01:25 PKT -- FileNotFoundError: BRIEF_WATCH_DIR does not exist: .../does-not-exist -- NEEDS HUMAN
```

`progress.md` tail (`evidence/05_progress_after_failure.md`):

```
## 2026-08-20 01:25 PKT

RUN FAILED -- needs a human.

- watch dir: .../does-not-exist
- error: FileNotFoundError: BRIEF_WATCH_DIR does not exist: .../does-not-exist
- state was NOT updated this run (nothing new was marked seen)
```

## Step 4 — diagnose from the spine alone

Full writeup: `evidence/06_diagnosis.md`. Reading only those two tails
above (no replaying the run, no opening the script):

- **What failed:** `BRIEF_WATCH_DIR` pointed at a directory that doesn't
  exist.
- **When:** 2026-08-20 01:25 PKT, on both lines.
- **Blast radius:** none — `state was NOT updated this run` confirms
  the spine wasn't corrupted, so nothing gets skipped once it's fixed.
- **Action:** a human fixes the path and re-runs.

## Step 5 — recovery

Removing the sabotage and running again resumes exactly where the spine
left off (`evidence/07_recovery_run_brief_log.txt`):

```
$ bash scripts/run_brief.sh; echo $?
0
```

`progress.md` tail — picks straight back up after the failure entry:

```
## 2026-08-20 01:25 PKT

Building on previous progress (see earlier entries below).

- No new commits in the last 24h.
- No new TODO comments.
```

## Evidence index

| File | What it shows |
|---|---|
| `evidence/01_baseline_run.txt` | Healthy first run, real `run_brief.sh` |
| `evidence/pre_fix_variant.py` | Script before the fix (for comparison only) |
| `evidence/02_before_fix_run.txt` | Sabotage against the pre-fix script: silent wrong success |
| `evidence/03_progress_after_silent_wrong_success.md` | The spine entry that hides the failure |
| `evidence/04_sabotaged_run_brief_log.txt` | Same sabotage, fixed script: loud failure in `brief.log` |
| `evidence/05_progress_after_failure.md` | The "needs a human" entry in `progress.md` |
| `evidence/06_diagnosis.md` | Diagnosis written from the spine alone |
| `evidence/07_recovery_run_brief_log.txt` | Loop resumes cleanly once fixed |

## Done-when checklist

- [x] What failed, and when, readable from `brief.log` + `progress.md` alone — `evidence/06_diagnosis.md`.
- [x] Clear "needs a human" note instead of a silent failure — fixed in `scripts/morning_brief.py`, proven against the original silent-success bug in `evidence/02-03`.
- [x] Monthly cost at current cadence known — $0.00/month (real, no model calls); ~$0.26–$0.39/month illustrative if AI-driven, both computed above with live Sonnet 5 pricing.
