"""Summary statistics for latency samples."""

import math
from collections.abc import Sequence


def percentile(samples: Sequence[float], p: float) -> float:
    """Return the p-th percentile of ``samples`` using the nearest-rank method.

    Nearest rank: sort the samples ascending and take the one at 1-based rank
    ``ceil(p / 100 * n)``. The result is always one of the samples (no interpolation).

    Rules (tests/test_stats.py checks every one):
    - ``samples`` does not have to be sorted. Do not modify the caller's sequence.
    - ``0 < p <= 100``, otherwise raise ``ValueError``.
    - Empty ``samples`` raises ``ValueError``.

    Useful: ``sorted(...)``, ``math.ceil(...)``. Python lists are 0-indexed, ranks are 1-based.
    Careful: floats are not exact (try ``14 / 100 * 100`` in a Python shell).
    """
    if p <= 0 or p > 100:
        raise ValueError(f"p must be in the range 0 < p <= 100, got {p}")
    if len(samples) == 0:
        raise ValueError("samples must not be empty")
    n = len(samples)
    samples_sorted = sorted(samples)
    return samples_sorted[math.ceil((n * p) / 100) - 1]
