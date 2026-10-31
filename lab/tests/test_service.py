"""Tests for the generic lab service (#73)."""

import asyncio
import time
from collections.abc import Callable, Coroutine
from typing import Any

import httpx
import pytest
from prometheus_client import REGISTRY

from chaosnet_lab.breaker import Breaker
from chaosnet_lab.service import Hop, app

Handler = Callable[[httpx.Request], Coroutine[None, None, httpx.Response]]


def hop(name: str, url: str) -> Hop:
    return Hop(name, url, timeout_s=0.5, max_retries=0)


def ask(name: str, calls: list[Hop], downstream: Handler) -> httpx.Response:
    """POST /orders to a service called `name` whose callees answer with `downstream`."""

    async def run() -> httpx.Response:
        async with httpx.AsyncClient(transport=httpx.MockTransport(downstream)) as client:
            app.state.name, app.state.calls, app.state.client = name, calls, client
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://svc") as c:
                return await c.post("/orders", json={"item_id": "42"})

    return asyncio.run(run())


def leaf(name: str) -> dict[str, Any]:
    return {"service": name, "calls": []}


async def answers_as_leaf(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=leaf(request.url.host))


def test_a_leaf_answers_at_once() -> None:
    res = ask("inventory", [], answers_as_leaf)
    assert res.status_code == 200
    assert res.json() == leaf("inventory")


def test_calls_every_callee_with_get_and_returns_their_answers_in_order() -> None:
    seen: list[str] = []

    async def downstream(request: httpx.Request) -> httpx.Response:
        seen.append(f"{request.method} {request.url}")
        return await answers_as_leaf(request)

    calls = [
        hop("orders->inventory", "http://inventory"),
        hop("orders->payments", "http://payments"),
    ]
    res = ask("orders", calls, downstream)
    assert res.json() == {"service": "orders", "calls": [leaf("inventory"), leaf("payments")]}
    assert sorted(seen) == ["GET http://inventory/orders", "GET http://payments/orders"]


def test_callees_are_called_at_the_same_time() -> None:
    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.2)
        return await answers_as_leaf(request)

    calls = [hop("a->b", "http://b"), hop("a->c", "http://c"), hop("a->d", "http://d")]
    start = time.perf_counter()
    assert ask("a", calls, slow).status_code == 200
    assert time.perf_counter() - start < 0.4, "one after another would take 0.6 s"


def test_one_unreachable_callee_fails_the_request_naming_its_hop() -> None:
    async def payments_down(request: httpx.Request) -> httpx.Response:
        if request.url.host == "payments":
            raise httpx.ConnectError("refused")
        return await answers_as_leaf(request)

    calls = [
        hop("orders->inventory", "http://inventory"),
        hop("orders->payments", "http://payments"),
    ]
    res = ask("orders", calls, payments_down)
    assert res.status_code == 503
    assert res.json() == {"error": "unavailable", "failed_hop": "orders->payments"}


def test_a_failure_further_down_is_passed_on_unchanged() -> None:
    async def failed_below(request: httpx.Request) -> httpx.Response:
        return httpx.Response(504, json={"error": "timeout", "failed_hop": "orders->inventory"})

    res = ask("gateway", [hop("gateway->orders", "http://orders")], failed_below)
    assert res.status_code == 504
    assert res.json()["failed_hop"] == "orders->inventory"


VALID = {
    "hop": "orders->inventory",
    "url": "http://toxiproxy:8666",
    "timeout_s": 0.5,
    "max_retries": 2,
}


def test_valid_call_config() -> None:
    assert Hop.parse(VALID) == Hop("orders->inventory", "http://toxiproxy:8666", 0.5, 2)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("url", ""),
        ("url", "toxiproxy:8666"),
        ("url", "htp://toxiproxy:8666"),
        ("url", "http://"),
        ("timeout_s", 0),
        ("max_retries", -1),
    ],
)
def test_invalid_call_config_fails_at_startup(key: str, value: object) -> None:
    with pytest.raises(ValueError, match=key):
        Hop.parse({**VALID, key: value})


def test_every_request_is_counted_and_shown_at_metrics() -> None:
    def requests() -> float:
        return REGISTRY.get_sample_value("lab_requests_total", {"service": "counted"}) or 0

    before = requests()
    ask("counted", [], answers_as_leaf)
    ask("counted", [], answers_as_leaf)
    assert requests() - before == 2

    async def scrape() -> str:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://svc") as c:
            return (await c.get("/metrics")).text

    assert 'lab_requests_total{service="counted"}' in asyncio.run(scrape())


# --- circuit breaker on a link (#136) ---------------------------------------------------


def test_an_open_breaker_answers_at_once_without_calling() -> None:
    called: list[str] = []

    async def down(request: httpx.Request) -> httpx.Response:
        called.append(str(request.url))
        raise httpx.ConnectError("refused")

    hop = Hop("orders->inventory", "http://inventory", 0.5, 0, breaker=Breaker())
    for _ in range(10):  # 10 failed calls: more than 50 % with the minimum of 10
        assert ask("orders", [hop], down).status_code == 503
    assert len(called) == 10

    def rejected() -> float:
        labels = {"hop": "orders->inventory", "outcome": "rejected"}
        return REGISTRY.get_sample_value("lab_attempts_total", labels) or 0

    before = rejected()
    res = ask("orders", [hop], down)
    assert res.status_code == 503
    assert res.json() == {"error": "circuit_open", "failed_hop": "orders->inventory"}
    assert len(called) == 10  # inventory was not called
    assert rejected() - before == 1


def test_a_failure_further_down_counts_for_the_breaker() -> None:
    async def failed_below(request: httpx.Request) -> httpx.Response:
        return httpx.Response(504, json={"error": "timeout", "failed_hop": "orders->inventory"})

    hop = Hop("gateway->orders", "http://orders", 2.0, 0, breaker=Breaker())
    for _ in range(10):
        ask("gateway", [hop], failed_below)
    assert ask("gateway", [hop], failed_below).json()["error"] == "circuit_open"


def test_a_breaker_comes_from_the_config_and_is_off_by_default() -> None:
    assert Hop.parse(VALID).breaker is None
    assert isinstance(Hop.parse({**VALID, "breaker": True}).breaker, Breaker)
