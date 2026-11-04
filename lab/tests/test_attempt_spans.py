"""One span per attempt in call_downstream (#158)."""

import asyncio

import httpx
import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from chaosnet_lab.client import DownstreamError, call_downstream

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
