"""Watchdog: removes all faults when heartbeats from the control plane stop (ADR-001, layer 3)."""


class Lease:
    """Time-limited permission for faults to stay active.

    Time is always passed in as ``now`` (seconds), never read from a clock here, so the
    logic can be tested without waiting. See tests/test_watchdog.py.
    """

    def __init__(self, timeout_s: float, now: float) -> None:
        raise NotImplementedError

    def renew(self, now: float) -> None:
        raise NotImplementedError

    def should_reset(self, now: float) -> bool:
        raise NotImplementedError
