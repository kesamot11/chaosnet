"""One span per attempt in call_downstream (#158)."""

import asyncio
from collections.abc import Awaitable, Callable

import httpx
import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from chaosnet_lab.breaker import Breaker
from chaosnet_lab.budget import RetryBudget
from chaosnet_lab.client import DownstreamError, call_downstream
from chaosnet_lab.service import Hop
from chaosnet_lab.service import call as service_call

EXPORTER = InMemorySpanExporter()
_provider = TracerProvider()
_provider.add_span_processor(SimpleSpanProcessor(EXPORTER))
trace.set_tracer_provider(_provider)  # once per process; spans land in EXPORTER


def call(script: list[int | Exception]) -> list[ReadableSpan]:
    """call_downstream with 2 retries inside a parent span; the attempt spans, in order."""
    EXPORTER.clear()
    steps = iter(script)

    def handle(request: httpx.Request) -> httpx.Response:
        step = next(steps)
        if isinstance(step, Exception):
            raise step
        return httpx.Response(step)

    async def go() -> None:
        tracer = trace.get_tracer("test")
        with tracer.start_as_current_span("orders GET"):
            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
                try:
                    await call_downstream(
                        client,
                        "GET",
                        "http://inventory/orders",
                        hop="orders->inventory",
                        timeout_s=0.5,
                        max_retries=2,
                    )
                except DownstreamError:
                    pass

    asyncio.run(go())
    spans = [s for s in EXPORTER.get_finished_spans() if s.name.startswith("attempt")]
    return sorted(spans, key=lambda s: s.start_time or 0)


def test_every_attempt_is_a_span_with_its_number_and_outcome() -> None:
    spans = call([httpx.ReadTimeout("t"), httpx.ConnectError("c"), 200])
    assert [s.name for s in spans] == ["attempt 1", "attempt 2", "attempt 3"]
    assert [(s.attributes or {}).get("chaosnet.attempt") for s in spans] == [1, 2, 3]
    outcomes = [(s.attributes or {}).get("chaosnet.outcome") for s in spans]
    assert outcomes == ["timeout", "connection_error", "ok"]


def test_attempts_are_children_of_the_call() -> None:
    spans = call([httpx.ReadTimeout("t"), 200])
    parent = next(s for s in EXPORTER.get_finished_spans() if s.name == "orders GET")
    assert len(spans) == 2
    assert parent.context is not None
    assert all(s.parent and s.parent.span_id == parent.context.span_id for s in spans)


@pytest.mark.parametrize(("script", "outcome"), [([200], "ok"), ([503], "http_error")])
def test_one_attempt_when_the_first_one_answers(
    script: list[int | Exception], outcome: str
) -> None:
    spans = call(script)
    assert [(s.name, (s.attributes or {}).get("chaosnet.outcome")) for s in spans] == [
        ("attempt 1", outcome)
    ]


# --- backoff and refusals (#158, second part) -------------------------------------------


def traced(coroutine_factory: Callable[[], Awaitable[object]]) -> ReadableSpan:
    """Run a coroutine inside a parent span "call"; return that span when finished."""
    EXPORTER.clear()

    async def go() -> None:
        with trace.get_tracer("test").start_as_current_span("call"):
            await coroutine_factory()

    asyncio.run(go())
    return next(s for s in EXPORTER.get_finished_spans() if s.name == "call")


def downstream(script: list[int | Exception]) -> httpx.AsyncClient:
    steps = iter(script)

    def handle(request: httpx.Request) -> httpx.Response:
        step = next(steps)
        if isinstance(step, Exception):
            raise step
        return httpx.Response(step)

    return httpx.AsyncClient(transport=httpx.MockTransport(handle))


def test_the_backoff_wait_is_a_span_between_the_attempts() -> None:
    async def no_sleep(seconds: float) -> None:
        pass

    async def run() -> None:
        async with downstream([httpx.ReadTimeout("t"), httpx.ReadTimeout("t"), 200]) as client:
            await call_downstream(
                client,
                "GET",
                "http://inventory/orders",
                hop="orders->inventory",
                timeout_s=0.5,
                max_retries=2,
                backoff_s=0.1,
                sleep=no_sleep,
            )

    parent = traced(run)
    spans = sorted(EXPORTER.get_finished_spans(), key=lambda s: s.start_time or 0)
    names = [s.name for s in spans if s.name.startswith(("attempt", "backoff"))]
    assert names == ["attempt 1", "backoff", "attempt 2", "backoff", "attempt 3"]
    waits = [(s.attributes or {}).get("chaosnet.wait_s") for s in spans if s.name == "backoff"]
    assert all(isinstance(w, float) and 0 <= w <= 0.2 for w in waits)
    assert parent.context is not None
    assert all(
        s.parent and s.parent.span_id == parent.context.span_id
        for s in spans
        if s.name == "backoff"
    )


def test_a_retry_refused_by_the_budget_is_an_event() -> None:
    budget = RetryBudget()
    budget.tokens = 0

    async def run() -> None:
        async with downstream([httpx.ReadTimeout("t")]) as client:
            try:
                await call_downstream(
                    client,
                    "GET",
                    "http://inventory/orders",
                    hop="orders->inventory",
                    timeout_s=0.5,
                    max_retries=2,
                    budget=budget,
                )
            except DownstreamError:
                pass

    parent = traced(run)
    events = [(e.name, dict(e.attributes or {})) for e in parent.events]
    assert events == [("retry refused", {"reason": "budget"})]


def test_a_call_refused_by_the_breaker_is_an_event() -> None:
    hop = Hop("orders->inventory", "http://inventory", 0.5, 0, breaker=Breaker())
    assert hop.breaker is not None
    hop.breaker.state, hop.breaker.opened_at = "open", hop.breaker.now()

    async def run() -> None:
        async with downstream([]) as client:
            await service_call(client, hop)

    parent = traced(run)
    events = [(e.name, dict(e.attributes or {})) for e in parent.events]
    assert events == [("circuit open", {"chaosnet.hop": "orders->inventory"})]
