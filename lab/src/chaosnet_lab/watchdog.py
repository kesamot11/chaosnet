"""Watchdog: removes all faults when heartbeats from the control plane stop (ADR-001, layer 3)."""

import asyncio
import time
from collections.abc import Awaitable, Callable


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


async def watch(
    lease: Lease,
    reset: Callable[[], Awaitable[None]],
    *,
    interval_s: float = 0.5,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """Forever: when the lease expires, call ``reset`` until it succeeds.

    A failing ``reset`` (Toxiproxy down) is retried every ``interval_s`` and must never
    stop the loop. See tests/test_watchdog.py.
    """
    pending = False
    while True:
        if lease.should_reset(clock()):
            pending = True
        if pending:
            try:
                await reset()
                pending = False
            except Exception:
                pass
        await asyncio.sleep(interval_s)
