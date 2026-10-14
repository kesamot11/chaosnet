"""Watchdog: removes all faults when heartbeats from the control plane stop (ADR-001, layer 3)."""


class Lease:
    """Time-limited permission for faults to stay active.

    Time is always passed in as ``now`` (seconds), never read from a clock here, so the
    logic can be tested without waiting. See tests/test_watchdog.py.
    """

    def __init__(self, timeout_s: float, now: float) -> None:
        if timeout_s <= 0:
            raise ValueError(f"Timeout needs to be greater than 0, got {timeout_s}")
        self.timeout_s = timeout_s
        self.last_beat = now
        self.reset_done = False

    def renew(self, now: float) -> None:
        self.last_beat = now
        self.reset_done = False

    def should_reset(self, now: float) -> bool:
        if now - self.last_beat >= self.timeout_s and not self.reset_done:
            self.reset_done = True
            return True
        return False
