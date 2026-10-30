"""The one service of the lab (#73): every node of topology.json runs this code.

It answers ``/orders`` by calling every service it links to, all at the same time, and
waits for all of them; a leaf (no links) answers at once. The shop of the first lab
(items, stock, 404 for an unknown item) is gone: experiments measure the network
between services, not business logic (plan in #73, decisions by Tomáš).

Configuration, written by the generator (backend/src/chaosnet/labgen.py):
- SERVICE_NAME: this service, e.g. "orders"
- CALLS: one entry per link from this service, as JSON, e.g.
  [{"hop": "orders->inventory", "url": "http://toxiproxy:8666", "timeout_s": 0.5,
    "max_retries": 2, "backoff_s": 0.0}]
"""

import asyncio
import json
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest

from chaosnet_lab.client import DownstreamError, call_downstream

# Counted by the service itself; a service that hangs counts nothing (#116, see client.py).
REQUESTS = Counter("lab_requests", "Requests this service received", ["service"])


@dataclass(frozen=True)
class Hop:
    name: str  # e.g. "orders->inventory"
    url: str  # the link's Toxiproxy proxy, so faults can be added per link
    timeout_s: float  # per attempt
    max_retries: int
    backoff_s: float = 0.0  # see client.retry_wait

    @classmethod
    def parse(cls, raw: dict[str, Any]) -> Hop:
        """One entry of CALLS; a bad value stops the service at startup, not at a request."""
        url = str(raw.get("url", ""))
        parsed = httpx.URL(url)
        if parsed.scheme not in ("http", "https") or not parsed.host:
            raise ValueError(f"url must be http(s)://host[:port], got {url!r}")
        timeout_s = float(raw["timeout_s"])
        max_retries = int(raw["max_retries"])
        if timeout_s <= 0:
            raise ValueError(f"timeout_s must be > 0, got {timeout_s}")
        if max_retries < 0:
            raise ValueError(f"max_retries must be >= 0, got {max_retries}")
        backoff_s = float(raw.get("backoff_s", 0.0))
        if backoff_s < 0:
            raise ValueError(f"backoff_s must be >= 0, got {backoff_s}")
        return cls(str(raw["hop"]), url, timeout_s, max_retries, backoff_s)


def calls_from_env() -> list[Hop]:
    return [Hop.parse(raw) for raw in json.loads(os.environ.get("CALLS", "[]"))]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    app.state.name = os.environ["SERVICE_NAME"]
    app.state.calls = calls_from_env()
    async with httpx.AsyncClient() as client:
        app.state.client = client
        yield


app = FastAPI(title="lab service", lifespan=lifespan)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
def metrics() -> Response:
    """Read by Prometheus inside the lab network; the service's port is never published."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# POST from the load generator at the entry, GET between services: a service changes
# nothing, so a call may be repeated, and call_downstream retries a GET after a timeout.
@app.api_route("/orders", methods=["GET", "POST"])
async def handle(request: Request) -> Response:
    state = request.app.state
    REQUESTS.labels(state.name).inc()
    # ponytail: waits for every callee even after one failed; cancel the rest if a slow
    # branch ever makes failures look slower than they are.
    answers = await asyncio.gather(*(call(state.client, hop) for hop in state.calls))
    for answer in answers:
        if isinstance(answer, Response):
            return answer  # the first failed callee, in topology order
    return JSONResponse({"service": state.name, "calls": answers})


async def call(client: httpx.AsyncClient, hop: Hop) -> dict[str, Any] | Response:
    """The callee's answer, or the response this service gives when the callee failed."""
    try:
        res = await call_downstream(
            client,
            "GET",
            hop.url + "/orders",
            hop=hop.name,
            timeout_s=hop.timeout_s,
            max_retries=hop.max_retries,
            backoff_s=hop.backoff_s,
        )
    except DownstreamError as e:
        reason = "unavailable" if e.status_code == 503 else "timeout"
        return JSONResponse({"error": reason, "failed_hop": e.failed_hop}, e.status_code)
    if res.is_error:  # the callee's own failure, e.g. a failed hop further down: pass it on
        return Response(res.content, res.status_code, media_type=res.headers.get("content-type"))
    body: dict[str, Any] = res.json()
    return body
