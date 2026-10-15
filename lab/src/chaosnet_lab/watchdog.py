"""Watchdog: removes all faults when heartbeats from the control plane stop (ADR-001, layer 3)."""

import asyncio
import os
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import httpx
from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse

FAILURE_LOG_EVERY_S = 10.0


def log(message: str) -> None:
    # UTC with an explicit Z everywhere, so CLI and watchdog logs line up (review of #43).
    print(f"{datetime.now(UTC):%Y-%m-%dT%H:%M:%SZ} watchdog: {message}", flush=True)


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
    failures = 0
    next_failure_log = 0.0
    while True:
        if lease.should_reset(clock()):
            pending = True
        if pending:
            try:
                await reset()
                pending = False
                after = f" after {failures} failed attempt(s)" if failures else ""
                log(f"lease expired: all faults removed{after}")
                failures = 0
            except Exception as e:
                failures += 1
                # One line per FAILURE_LOG_EVERY_S, not one per attempt (review of #43).
                if clock() >= next_failure_log:
                    log(f"reset failing ({failures} attempt(s)): {type(e).__name__}: {e}")
                    next_failure_log = clock() + FAILURE_LOG_EVERY_S
        await asyncio.sleep(interval_s)


# --- the service: heartbeat endpoint + the loop above running in the background ---------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    toxiproxy_url = os.environ.get("TOXIPROXY_URL", "http://toxiproxy:8474")
    lease_timeout_s = float(os.environ.get("LEASE_TIMEOUT_S", "5"))
    check_interval_s = float(os.environ.get("CHECK_INTERVAL_S", "0.5"))
    if not 0 < check_interval_s < lease_timeout_s:
        raise ValueError(
            "need 0 < CHECK_INTERVAL_S < LEASE_TIMEOUT_S, "
            f"got {check_interval_s=}, {lease_timeout_s=}"
        )

    async with httpx.AsyncClient() as client:

        async def reset_toxiproxy() -> None:
            res = await client.post(f"{toxiproxy_url}/reset", timeout=2)
            res.raise_for_status()

        app.state.lease = Lease(lease_timeout_s, now=time.monotonic())
        task = asyncio.create_task(
            watch(app.state.lease, reset_toxiproxy, interval_s=check_interval_s)
        )
        task.add_done_callback(
            lambda t: t.cancelled() or log(f"watch loop stopped: {t.exception()!r}")
        )
        app.state.watch_task = task
        log(f"lease {lease_timeout_s} s, checking every {check_interval_s} s")
        yield
        task.cancel()


app = FastAPI(title="watchdog", lifespan=lifespan)


@app.get("/healthz")
def healthz() -> Response:
    # Healthy only while the loop that guards the lease is running: a live HTTP server
    # with a dead loop would look fine and protect nothing (review of #43).
    if app.state.watch_task.done():
        return JSONResponse({"status": "watch loop stopped"}, status_code=503)
    return JSONResponse({"status": "ok"})


@app.post("/heartbeat", status_code=204)
def heartbeat() -> Response:
    app.state.lease.renew(now=time.monotonic())
    return Response(status_code=204)
