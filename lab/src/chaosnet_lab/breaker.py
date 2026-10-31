"""Circuit breaker for one link, kept by the caller (#135, ADR-008).

    closed ──(> 50 % of the calls in the last 10 s failed, at least 10 calls)──► open
    open ──(5 s cooldown)──► half-open: one trial call
    half-open ──(trial ok)──► closed        half-open ──(trial failed)──► open

No I/O and no real clock: `now` is passed in, so tests do not wait.
"""

import time
from collections.abc import Callable
from typing import Literal

State = Literal["closed", "open", "half_open"]


class Breaker:
    def __init__(
        self,
        *,
        window_s: float = 10.0,
        min_calls: int = 10,
        failure_rate: float = 0.5,  # opens above this share of failures
        cooldown_s: float = 5.0,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self.window_s = window_s
        self.min_calls = min_calls
        self.failure_rate = failure_rate
        self.cooldown_s = cooldown_s
        self.now = now
        # What the breaker remembers (plan by Tomáš, 2026-10-31):
        self.state: State = "closed"
        self.calls: list[tuple[float, bool]] = []  # (time, ok) of each call in the window
        self.opened_at = 0.0  # when it last opened, for the cooldown
        self.trial_in_flight = False  # half-open lets one trial call through

    def allow(self) -> bool:
        """May the caller make a call now? In half-open, True once, for the trial."""
        raise NotImplementedError("Tomáš, #135, step 2")

    def record(self, ok: bool) -> None:
        """How the call allowed by allow() ended."""
        raise NotImplementedError("Tomáš, #135, step 3")
