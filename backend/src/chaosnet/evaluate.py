"""Measuring a detector on the labelled runs (#255, ADR-013)."""

from typing import Any

from sklearn.model_selection import GroupKFold  # pyright: ignore[reportMissingTypeStubs]


def folds(rows: list[dict[str, Any]], k: int = 5) -> list[tuple[list[int], list[int]]]:
    """Train and test rows, split by run: one run's seconds never land on both sides.

    Neighbouring seconds of a run are nearly the same, so a split by second would leak them
    into the test and the score would lie (ADR-013, decision 5).
    """
    runs = [r["run"] for r in rows]
    # scikit-learn has no type stubs; the indices it gives are numpy ints
    split = GroupKFold(n_splits=k).split(runs, groups=runs)  # pyright: ignore[reportUnknownMemberType]
    return [([int(i) for i in train], [int(i) for i in test]) for train, test in split]
