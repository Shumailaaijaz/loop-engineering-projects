"""Budget guards for the Project 8 daily loop.

Every limit here is a hard cap, not a target. Exceeding any of them means
the loop stops *before* the Connector step and never publishes. See
README.md ("Budget Guards") for the reasoning behind each number.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Budget:
    max_runtime_seconds: int = 120          # per iteration (deterministic maker)
    max_runtime_seconds_llm: int = 240      # per iteration when MAKER_CLI=claude
    max_files_changed: int = 1              # README.md only
    max_lines_changed: int = 60             # generous margin over the ~8 lines expected
    max_repair_attempts: int = 1            # bounded retry after a Checker FAIL
    max_consecutive_failures: int = 3       # circuit breaker -> state/STOP
    max_runs_per_day: int = 1               # independent of cron cadence
    max_model_calls_per_run: int = 1        # only spent in MAKER_CLI=claude mode


BUDGET = Budget()


class BudgetExceeded(Exception):
    """Raised when a run would exceed a hard budget guard.

    Caught exactly once, at the top of loop.py's run(): it always means
    "stop safely, do not publish, record why" — never a retry.
    """
