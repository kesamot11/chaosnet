import asyncio
import time

import pytest

from chaosnet_lab.watchdog import Lease, watch


def test_fresh_lease_does_not_reset_before_timeout() -> None:
    lease = Lease(timeout_s=5, now=0)
    assert not lease.should_reset(now=4.9)


def test_after_a_restart_the_watchdog_waits_a_full_timeout() -> None:
    # A lease starts when the watchdog starts: a live CLI has 5 s to send a heartbeat.
    lease = Lease(timeout_s=5, now=100)
    assert not lease.should_reset(now=104)
    assert lease.should_reset(now=105)


def test_resets_when_no_heartbeat_arrives_within_timeout() -> None:
    lease = Lease(timeout_s=5, now=0)
    assert lease.should_reset(now=5)


def test_heartbeat_extends_the_lease_from_the_moment_it_arrives() -> None:
    lease = Lease(timeout_s=5, now=0)
    lease.renew(now=3)
    assert not lease.should_reset(now=7.9)
    assert lease.should_reset(now=8)


def test_regular_heartbeats_never_trigger_a_reset() -> None:
    lease = Lease(timeout_s=5, now=0)
    for second in range(1, 61):
        lease.renew(now=second)
        assert not lease.should_reset(now=second + 0.5)


def test_reset_is_requested_only_once_per_expiry() -> None:
    lease = Lease(timeout_s=5, now=0)
    assert lease.should_reset(now=6)
    assert not lease.should_reset(now=7)
    assert not lease.should_reset(now=60)


def test_heartbeat_after_a_reset_re_arms_the_lease() -> None:
    lease = Lease(timeout_s=5, now=0)
    assert lease.should_reset(now=6)
    lease.renew(now=12)
    assert not lease.should_reset(now=16)
    assert lease.should_reset(now=17)


@pytest.mark.parametrize("timeout_s", [0, -1])
def test_non_positive_timeout_is_rejected(timeout_s: float) -> None:
    with pytest.raises(ValueError, match=str(timeout_s)):
        Lease(timeout_s=timeout_s, now=0)


# --- the background loop ---------------------------------------------------------------


class FakeReset:
    """Stands in for POST /reset on Toxiproxy; can fail the first N calls."""

    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.calls = 0

    async def __call__(self) -> None:
        self.calls += 1
        if self.calls <= self.failures:
            raise ConnectionError("toxiproxy unreachable")


def run_watch(lease: Lease, reset: FakeReset, *, seconds: float, renew_every: float = 0) -> None:
    async def go() -> None:
        loop = asyncio.get_running_loop()
        watcher = asyncio.create_task(watch(lease, reset, interval_s=0.01, clock=loop.time))
        end = loop.time() + seconds
        while loop.time() < end:
            if renew_every:
                lease.renew(loop.time())
            await asyncio.sleep(renew_every or 0.01)
        watcher.cancel()

    asyncio.run(go())


def test_resets_once_when_heartbeats_stop() -> None:
    reset = FakeReset()
    run_watch(Lease(timeout_s=0.05, now=0), reset, seconds=0.3)
    assert reset.calls == 1


def test_never_resets_while_heartbeats_arrive() -> None:
    reset = FakeReset()
    lease = Lease(timeout_s=0.1, now=time.monotonic())  # the event loop clock
    run_watch(lease, reset, seconds=0.3, renew_every=0.02)
    assert reset.calls == 0


def test_failed_reset_is_retried_until_it_succeeds() -> None:
    reset = FakeReset(failures=2)
    run_watch(Lease(timeout_s=0.05, now=0), reset, seconds=0.3)
    assert reset.calls == 3  # two failures, one success, then nothing more
