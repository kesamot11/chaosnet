"""Measuring a detector on the labelled runs (#255, ADR-013).

uv run chaosnet-evaluate ../data/runs.csv
"""

import csv
import statistics
import sys
from collections.abc import Callable
from typing import Any

from sklearn.model_selection import GroupKFold  # pyright: ignore[reportMissingTypeStubs]

from chaosnet.dataset import LINKS

Row = dict[str, Any]
Detector = Callable[[Row], str | None]  # a second → the link it blames, None when all is well

P95_LIMIT_MS = 100  # Tomáš: about 3× the highest normal p95 (33 ms), so noise never alarms
FAILED = ["http_error", "timeout", "connection_error", "rejected"]  # rejected: an open breaker


def folds(rows: list[Row], k: int = 5) -> list[tuple[list[int], list[int]]]:
    """Train and test rows, split by run: one run's seconds never land on both sides.

    Neighbouring seconds of a run are nearly the same, so a split by second would leak them
    into the test and the score would lie (ADR-013, decision 5).
    """
    runs = [r["run"] for r in rows]
    # scikit-learn has no type stubs; the indices it gives are numpy ints
    split = GroupKFold(n_splits=k).split(runs, groups=runs)  # pyright: ignore[reportUnknownMemberType]
    return [([int(i) for i in train], [int(i) for i in test]) for train, test in split]


def number(row: Row, column: str) -> float:
    """A cell as a number; empty is 0 (an outcome that never happened, Tomáš, #254)."""
    return float(row.get(column) or 0)


def rule(row: Row) -> str | None:
    """The baseline (ADR-013, decision 2): the deepest link that has a problem.

    A link has a problem when its p95 is over the limit or any attempt on it failed. A slow
    callee makes every link above it slow too, because the callers wait, so the deepest one
    is the cause.
    """
    # ponytail: LINKS is this lab's chain, top first; a tree needs depths
    for link in reversed(LINKS):
        if number(row, f"{link} p95_ms") > P95_LIMIT_MS or any(
            number(row, f"{link} {o}") > 0 for o in FAILED
        ):
            return link
    return None


def measure(rows: list[Row], detect: Detector) -> dict[str, float]:
    """The four numbers of ADR-013 (decision 6) for a detector on these rows."""
    alarms = [(r, link) for r in rows if (link := detect(r)) is not None]
    true_alarms = [(r, link) for r, link in alarms if r["fault"] == "1"]
    faults = [r for r in rows if r["fault"] == "1"]
    delays: list[int] = []  # per run with a fault: seconds from its start to the first alarm
    for run in {r["run"] for r in faults}:
        seconds = [int(r["second"]) for r in faults if r["run"] == run]
        found = [int(r["second"]) for r, _ in true_alarms if r["run"] == run]
        if found:
            delays.append(min(found) - min(seconds))
    return {
        "precision": len(true_alarms) / len(alarms) if alarms else 0,
        "recall": len(true_alarms) / len(faults) if faults else 0,
        "detection delay s (median)": statistics.median(delays) if delays else float("nan"),
        "runs never detected": len({r["run"] for r in faults}) - len(delays),
        "root-cause accuracy": (
            sum(link == r["fault_link"] for r, link in true_alarms) / len(true_alarms)
            if true_alarms
            else 0
        ),
    }


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "../data/runs.csv"
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    for name, value in measure(rows, rule).items():
        print(f"{name:28} {value:.2f}" if isinstance(value, float) else f"{name:28} {value}")
