"""Calls between services: per-attempt timeout, retries, and error classification."""

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from opentelemetry import trace
from prometheus_client import Counter

from chaosnet_lab.budget import RetryBudget

# Counted by the caller, so attempts to a service that hangs are counted too (#116).
ATTEMPTS = Counter("lab_attempts", "Attempts to call another service", ["hop", "outcome"])
RETRIES_DENIED = Counter("lab_retries_denied", "Retries the retry budget refused", ["hop"])

# Spans for every attempt (#158); a no-op unless tracing is set up (tracing.py).
tracer = trace.get_tracer("chaosnet_lab.client")


def retry_wait(attempt: int, backoff_s: float, rand: float) -> float:
    """Seconds to wait after failed attempt number `attempt` (from 0), before the next one.

    Exponential backoff with full jitter (#119): up to backoff_s × 2^attempt, scaled by
    `rand` (0.0–1.0, random.random() in real calls), so callers that failed together do
    not all retry at the same moment. backoff_s 0 means retry at once, as before.
    """
    return ((2**attempt) * backoff_s) * rand


class DownstreamError(Exception):
    """A downstream service could not be reached after all attempts."""

    def __init__(self, status_code: int, failed_hop: str) -> None:
        super().__init__(f"{failed_hop} failed with {status_code}")
        self.status_code = status_code  # 503 = unavailable, 504 = timed out
        self.failed_hop = failed_hop  # e.g. "orders->inventory"


async def call_downstream(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    hop: str,
    timeout_s: float,
    max_retries: int,
    backoff_s: float = 0.0,
    budget: RetryBudget | None = None,
    json: Any = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> httpx.Response:
    """Call another service, retrying transport failures.

    Rules (tests/test_client.py checks every one):
    - At most ``max_retries + 1`` attempts in total. Between two attempts it waits
      ``retry_wait`` (backoff with jitter, #119); with ``backoff_s`` 0 it retries at once.
    - With a ``budget`` (#138), the first attempt earns it a share of a token and every
      retry must take a whole one; refused, the failure is final at once.
    - Every attempt uses ``timeout_s`` as its own timeout (not a total budget).
    - Any HTTP response (200, 404, 500, ...) is returned as-is, without retrying.
      Deciding what a status code means is the caller's job.

    Transport failures. The key question: was the request already sent?
    - Not sent (``ConnectError``, ``ConnectTimeout``): always retried.
    - Maybe processed (``ReadError``, ``RemoteProtocolError``, other timeouts): retried only
      for GET. Repeating a non-idempotent request (e.g. POST "pay") could apply it twice.
    - When no attempt is left: timeouts raise ``DownstreamError(504, hop)``, everything
      else ``DownstreamError(503, hop)``.
    """
    if max_retries < 0:
        raise ValueError(f"max_retries must be >= 0, not {max_retries}")
    code = 503
    if budget is not None:
        budget.first_attempt()
    for attempt in range(max_retries + 1):
        with tracer.start_as_current_span(f"attempt {attempt + 1}") as span:
            span.set_attribute("chaosnet.attempt", attempt + 1)
            try:
                res = await client.request(method, url, json=json, timeout=timeout_s)
                ATTEMPTS.labels(hop, "http_error" if res.is_error else "ok").inc()
                span.set_attribute("chaosnet.outcome", "http_error" if res.is_error else "ok")
                return res
            except httpx.ConnectError:
                ATTEMPTS.labels(hop, "connection_error").inc()
                span.set_attribute("chaosnet.outcome", "connection_error")
                code = 503
            except httpx.ReadError, httpx.RemoteProtocolError:
                ATTEMPTS.labels(hop, "connection_error").inc()
                span.set_attribute("chaosnet.outcome", "connection_error")
                code = 503
                if method != "GET":
                    break
            except httpx.ConnectTimeout:
                ATTEMPTS.labels(hop, "timeout").inc()
                span.set_attribute("chaosnet.outcome", "timeout")
                code = 504
            except httpx.TimeoutException:
                ATTEMPTS.labels(hop, "timeout").inc()
                span.set_attribute("chaosnet.outcome", "timeout")
                code = 504
                if method != "GET":
                    break
        if attempt == max_retries:
            break
        if budget is not None and not budget.try_retry():
            RETRIES_DENIED.labels(hop).inc()
            # Tomáš, #158: an event "retry refused" on the current span, reason "budget"
            break
        if backoff_s > 0:
            # Tomáš, #158: the wait as a span "backoff", attribute chaosnet.wait_s
            await sleep(retry_wait(attempt, backoff_s, random.random()))

    raise DownstreamError(code, hop)
