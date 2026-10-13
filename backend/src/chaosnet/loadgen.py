"""Open-model load generator.

Requests are scheduled at a constant rate, independent of how fast the target
answers, and latency is measured from the *scheduled* send time. A closed-loop
client (send, wait, send) would stop sending while the target is slow and hide
exactly the latency we want to see: coordinated omission.

    uv run python -m chaosnet.loadgen http://localhost:8080/orders --rate 50 --duration 10 \
        --body '{"item_id": "42"}'
"""

import argparse
import asyncio
import json
import time
from collections import Counter
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from chaosnet.stats import percentile

Outcome = Literal["ok", "http_4xx", "http_5xx", "timeout", "connection_error", "dropped"]


@dataclass(frozen=True)
class Sample:
    scheduled_s: float  # offset from the start of the run
    send_lag_s: float  # how late the generator itself was in sending
    latency_s: float  # from scheduled send time until the outcome was known
    outcome: Outcome


async def run_load(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    rate: float,
    duration_s: float,
    timeout_s: float,
    max_in_flight: int,
    json_body: Any = None,
) -> list[Sample]:
    """Send ``rate * duration_s`` requests on a fixed schedule and record each outcome.

    When ``max_in_flight`` requests are already pending, the request is recorded as
    ``dropped`` instead of waiting for a free slot: waiting would reintroduce
    coordinated omission.
    """
    if rate <= 0 or duration_s <= 0 or timeout_s <= 0 or max_in_flight < 1:
        raise ValueError(
            "rate, duration_s and timeout_s must be > 0 and max_in_flight >= 1, got "
            f"{rate=}, {duration_s=}, {timeout_s=}, {max_in_flight=}"
        )

    samples: list[Sample] = []
    tasks: set[asyncio.Task[None]] = set()
    start = time.perf_counter()

    async def send(scheduled: float, send_lag: float) -> None:
        try:
            res = await client.request(method, url, json=json_body, timeout=timeout_s)
            outcome: Outcome = (
                "http_5xx" if res.status_code >= 500 else "http_4xx" if res.is_error else "ok"
            )
        except httpx.TimeoutException:
            outcome = "timeout"
        except httpx.TransportError:
            outcome = "connection_error"
        latency = time.perf_counter() - scheduled
        samples.append(Sample(scheduled - start, send_lag, latency, outcome))

    for i in range(round(rate * duration_s)):
        scheduled = start + i / rate
        delay = scheduled - time.perf_counter()
        if delay > 0:
            await asyncio.sleep(delay)
        send_lag = max(0.0, time.perf_counter() - scheduled)
        if len(tasks) >= max_in_flight:
            samples.append(Sample(scheduled - start, send_lag, 0.0, "dropped"))
            continue
        task = asyncio.create_task(send(scheduled, send_lag))
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    await asyncio.gather(*tasks)
    return sorted(samples, key=lambda s: s.scheduled_s)


def summarize(samples: list[Sample], *, rate: float, duration_s: float) -> dict[str, Any]:
    """Aggregate samples into the JSON report described in #14."""

    def latency_ms(values: list[float]) -> dict[str, float] | None:
        if not values:
            return None
        ms = [v * 1000 for v in values]
        return {f"p{p:g}": round(percentile(ms, p), 2) for p in (50, 95, 99, 100)}

    sent = [s for s in samples if s.outcome != "dropped"]
    return {
        "target_rate": rate,
        "duration_s": duration_s,
        "scheduled": len(samples),
        "sent": len(sent),
        "outcomes": dict(Counter(s.outcome for s in samples)),
        # "ok" is what successful users saw; "all" also counts fast failures,
        # which would otherwise make a broken service look fast.
        "latency_ms": {
            "ok": latency_ms([s.latency_s for s in sent if s.outcome == "ok"]),
            "all": latency_ms([s.latency_s for s in sent]),
        },
        # If this grows, the generator (not the target) is the bottleneck and the run is invalid.
        "send_lag_ms": latency_ms([s.send_lag_s for s in samples]),
    }


async def _main(args: argparse.Namespace) -> dict[str, Any]:
    async with httpx.AsyncClient(limits=httpx.Limits(max_connections=args.max_in_flight)) as client:
        samples = await run_load(
            client,
            args.method,
            args.url,
            rate=args.rate,
            duration_s=args.duration,
            timeout_s=args.timeout,
            max_in_flight=args.max_in_flight,
            json_body=json.loads(args.body) if args.body else None,
        )
    return summarize(samples, rate=args.rate, duration_s=args.duration)


def main() -> None:
    parser = argparse.ArgumentParser(description="Open-model load generator.")
    parser.add_argument("url")
    parser.add_argument("--method", default="POST")
    parser.add_argument("--body", help="JSON request body")
    parser.add_argument("--rate", type=float, default=20, help="requests per second")
    parser.add_argument("--duration", type=float, default=10, help="seconds")
    parser.add_argument("--timeout", type=float, default=5, help="per-request timeout, seconds")
    parser.add_argument("--max-in-flight", type=int, default=500)
    print(json.dumps(asyncio.run(_main(parser.parse_args())), indent=2))


if __name__ == "__main__":
    main()
