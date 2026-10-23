import asyncio
import time
from collections.abc import Callable, Coroutine
from typing import Any

import httpx
import pytest

from chaosnet.loadgen import Sample, per_second, run_load, summarize

Handler = Callable[[httpx.Request], Coroutine[Any, Any, httpx.Response]]


def load(
    handler: Handler, *, rate: float, duration_s: float, max_in_flight: int = 100
) -> list[Sample]:
    async def go() -> list[Sample]:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await run_load(
                client,
                "GET",
                "http://target/",
                rate=rate,
                duration_s=duration_s,
                timeout_s=5,
                max_in_flight=max_in_flight,
            )

    return asyncio.run(go())


def slow(seconds: float) -> Handler:
    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(seconds)
        return httpx.Response(200)

    return handler


def test_schedule_does_not_wait_for_slow_responses() -> None:
    # Each response takes 200 ms, but requests must still go out every 20 ms.
    samples = load(slow(0.2), rate=50, duration_s=0.4)
    assert len(samples) == 20
    assert all(s.outcome == "ok" for s in samples)
    assert [round(s.scheduled_s, 3) for s in samples] == [round(i / 50, 3) for i in range(20)]
    assert max(s.send_lag_s for s in samples) < 0.02
    assert min(s.latency_s for s in samples) >= 0.2


def test_freeze_is_visible_not_hidden() -> None:
    # The target freezes between 0.3 s and 0.7 s; requests arriving then wait until 0.7 s.
    start: list[float] = []

    async def freezing(request: httpx.Request) -> httpx.Response:
        now = time.perf_counter()
        if not start:
            start.append(now)
        offset = now - start[0]
        if 0.3 <= offset < 0.7:
            await asyncio.sleep(0.7 - offset)
        return httpx.Response(200)

    samples = load(freezing, rate=50, duration_s=1.0)
    assert len(samples) == 50, "no request may be skipped while the target is frozen"
    slow_samples = [s for s in samples if s.latency_s > 0.05]
    # 20 requests are scheduled inside the freeze; a closed-loop client would record ~1.
    assert 18 <= len(slow_samples) <= 21
    assert max(s.latency_s for s in samples) >= 0.35


def test_outcomes_are_classified() -> None:
    answers: list[httpx.Response | Exception] = [
        httpx.Response(200),
        httpx.Response(404),
        httpx.Response(503),
        httpx.ReadTimeout("timed out"),
        httpx.ConnectError("refused"),
    ]
    calls = iter(answers)

    async def handler(request: httpx.Request) -> httpx.Response:
        answer = next(calls)
        if isinstance(answer, Exception):
            raise answer
        return answer

    samples = load(handler, rate=100, duration_s=0.05)
    assert [s.outcome for s in samples] == [
        "ok",
        "http_4xx",
        "http_5xx",
        "timeout",
        "connection_error",
    ]


def test_requests_beyond_max_in_flight_are_dropped_not_delayed() -> None:
    samples = load(slow(0.5), rate=100, duration_s=0.1, max_in_flight=3)
    outcomes = [s.outcome for s in samples]
    assert outcomes.count("ok") == 3
    assert outcomes.count("dropped") == 7
    # Dropping must not slow the schedule down.
    assert max(s.send_lag_s for s in samples) < 0.02


def test_invalid_parameters_rejected_with_actual_values() -> None:
    with pytest.raises(ValueError, match=r"rate=0, duration_s=1"):
        load(slow(0), rate=0, duration_s=1)


def test_summary_separates_ok_latency_from_fast_failures() -> None:
    samples = [Sample(i / 10, 0.0, 0.1, "ok") for i in range(8)] + [
        Sample(0.8, 0.0, 0.001, "http_5xx"),
        Sample(0.9, 0.001, 0.0, "dropped"),
    ]
    report = summarize(samples, rate=10, duration_s=1)
    assert report["scheduled"] == 10
    assert report["sent"] == 9
    assert report["outcomes"] == {"ok": 8, "http_5xx": 1, "dropped": 1}
    assert report["latency_ms"]["ok"]["p50"] == 100.0
    assert report["latency_ms"]["all"]["p100"] == 100.0
    assert report["send_lag_ms"]["p100"] == 1.0


# --- per_second (#62) -------------------------------------------------------------------


def test_per_second_groups_requests_by_the_second_they_were_sent() -> None:
    samples = [
        Sample(0.1, 0.0, 0.010, "ok"),
        Sample(0.6, 0.0, 0.010, "ok"),
        Sample(1.2, 0.0, 0.030, "ok"),
        Sample(1.7, 0.0, 0.050, "ok"),
    ]
    assert per_second(samples) == [
        {"second": 0, "p50": 10.0, "p95": 10.0, "error_rate": 0.0},
        {"second": 1, "p50": 30.0, "p95": 50.0, "error_rate": 0.0},
    ]


def test_per_second_a_slow_answer_stays_in_the_second_it_was_sent() -> None:
    # sent at 0.5, answered at 5.5: the graph must show it at 0, where the user waited
    assert per_second([Sample(0.5, 0.0, 5.0, "timeout")]) == [
        {"second": 0, "p50": 5000.0, "p95": 5000.0, "error_rate": 1.0},
    ]


def test_per_second_a_second_without_requests_is_a_gap_not_left_out() -> None:
    samples = [Sample(0.0, 0.0, 0.010, "ok"), Sample(2.0, 0.0, 0.010, "ok")]
    assert per_second(samples)[1] == {"second": 1, "p50": None, "p95": None, "error_rate": None}
    assert len(per_second(samples)) == 3


def test_per_second_failures_have_latency_too() -> None:
    samples = [Sample(0.1, 0.0, 0.002, "connection_error"), Sample(0.2, 0.0, 0.004, "http_5xx")]
    assert per_second(samples) == [
        {"second": 0, "p50": 2.0, "p95": 4.0, "error_rate": 1.0},
    ]


def test_per_second_dropped_requests_are_errors_without_latency() -> None:
    # never sent, so no latency, but a user was scheduled and got nothing
    samples = [Sample(0.1, 0.0, 0.010, "ok"), Sample(0.2, 0.3, 0.0, "dropped")]
    assert per_second(samples)[0] == {"second": 0, "p50": 10.0, "p95": 10.0, "error_rate": 0.5}
    only_dropped = per_second([Sample(0.2, 0.3, 0.0, "dropped")])
    assert only_dropped == [{"second": 0, "p50": None, "p95": None, "error_rate": 1.0}]


def test_per_second_a_request_at_exactly_3_0_belongs_to_second_3() -> None:
    samples = [Sample(2.999, 0.0, 0.010, "ok"), Sample(3.0, 0.0, 0.020, "ok")]
    assert [(s["second"], s["p50"]) for s in per_second(samples)] == [
        (0, None),
        (1, None),
        (2, 10.0),
        (3, 20.0),
    ]


def test_per_second_of_nothing_is_empty() -> None:
    assert per_second([]) == []


def test_summary_contains_the_series() -> None:
    report = summarize([Sample(0.1, 0.0, 0.010, "ok")], rate=1, duration_s=1)
    assert report["per_second"] == [{"second": 0, "p50": 10.0, "p95": 10.0, "error_rate": 0.0}]
