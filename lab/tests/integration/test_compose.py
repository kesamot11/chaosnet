"""Acceptance tests for #13 against the real Docker Compose lab.

Run with `make integration`. Uses its own Compose project and port, so it does not
touch a lab you are running for development.
"""

import json
import os
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.integration

LAB_DIR = Path(__file__).parents[2]
PORT = "18080"
TOXIPROXY_PORT = "18474"
WATCHDOG_PORT = "18475"
ENV = {
    **os.environ,
    "COMPOSE_PROJECT_NAME": "chaosnet-lab-test",
    "GATEWAY_PORT": PORT,
    "TOXIPROXY_PORT": TOXIPROXY_PORT,
    "WATCHDOG_PORT": WATCHDOG_PORT,
}
# orders->inventory defaults from compose.yaml: 0.5 s timeout, 2 retries
ORDERS_BUDGET_S = (2 + 1) * 0.5


def compose(*args: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["docker", "compose", *args],
        cwd=LAB_DIR,
        env=env or ENV,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def unpause(service: str) -> None:
    """Unpause and wait for health: Docker reports a paused container as unhealthy
    until its next successful probe after unpausing (verified in #13)."""
    compose("unpause", service)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        container = compose("ps", "-q", service).strip()
        health = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Health.Status}}", container],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        if health == "healthy":
            return
        time.sleep(0.2)
    raise TimeoutError(f"{service} not healthy 10 s after unpause")


def order(item_id: str = "42") -> tuple[httpx.Response, float]:
    start = time.perf_counter()
    res = httpx.post(f"http://127.0.0.1:{PORT}/orders", json={"item_id": item_id}, timeout=10)
    return res, time.perf_counter() - start


@pytest.fixture(scope="module", autouse=True)
def lab() -> Iterator[None]:
    compose("up", "-d", "--build", "--wait")
    yield
    compose("down", "--remove-orphans")


def test_all_services_are_healthy() -> None:
    services = [json.loads(line) for line in compose("ps", "--format", "json").splitlines()]
    assert {s["Service"]: s["Health"] for s in services} == {
        "gateway": "healthy",
        "orders": "healthy",
        "inventory": "healthy",
        "toxiproxy": "healthy",
        "watchdog": "healthy",
    }


def test_request_flows_through_all_services() -> None:
    res, _ = order("42")
    assert res.status_code == 200
    assert res.json()["item"]["item_id"] == "42"
    assert res.json()["path"] == ["gateway", "orders", "inventory"]


def test_unknown_item_is_404_end_to_end() -> None:
    res, _ = order("does-not-exist")
    assert res.status_code == 404


def test_only_gateway_and_control_apis_are_published() -> None:
    services = [json.loads(line) for line in compose("ps", "--format", "json").splitlines()]
    published = {s["Service"] for s in services if any(p["PublishedPort"] for p in s["Publishers"])}
    # gateway for traffic; toxiproxy and watchdog are control APIs; services stay internal
    assert published == {"gateway", "toxiproxy", "watchdog"}


def test_stopped_inventory_gives_fast_503_then_recovers() -> None:
    compose("stop", "inventory")
    try:
        res, elapsed = order()
        assert res.status_code == 503
        assert res.json()["failed_hop"] == "orders->inventory"
        assert elapsed < 0.5, "connection failures must not wait for a timeout"
    finally:
        compose("up", "-d", "--wait", "inventory")
    res, _ = order()
    assert res.status_code == 200


def test_hanging_inventory_gives_504_within_budget_then_recovers() -> None:
    compose("pause", "inventory")
    try:
        res, elapsed = order()
        assert res.status_code == 504
        assert res.json()["failed_hop"] == "orders->inventory"
        assert ORDERS_BUDGET_S <= elapsed < ORDERS_BUDGET_S + 0.5
    finally:
        unpause("inventory")
    res, _ = order()
    assert res.status_code == 200


def test_retries_are_configurable_without_rebuild() -> None:
    no_retries = {**ENV, "ORDERS_MAX_RETRIES": "0"}
    compose("up", "-d", "--wait", "--no-build", "orders", env=no_retries)
    compose("pause", "inventory")
    try:
        res, elapsed = order()
        assert res.status_code == 504
        assert 0.5 <= elapsed < 1.0, "one attempt of 0.5 s, not three"
    finally:
        unpause("inventory")
        compose("up", "-d", "--wait", "--no-build", "orders")


def test_proxies_survive_a_toxiproxy_restart() -> None:
    # A plain restart forgets proxies (#12); the config file must recreate them.
    compose("restart", "toxiproxy")
    compose("up", "-d", "--wait", "toxiproxy")
    proxies = httpx.get(f"http://127.0.0.1:{TOXIPROXY_PORT}/proxies", timeout=5).json()
    assert set(proxies) == {"gateway-orders", "orders-inventory"}
    res, _ = order()
    assert res.status_code == 200


def toxics_on(link: str) -> list[str]:
    proxies = httpx.get(f"http://127.0.0.1:{TOXIPROXY_PORT}/proxies", timeout=5).json()
    return [t["name"] for t in proxies[link]["toxics"]]


def test_watchdog_keeps_faults_while_heartbeats_arrive_then_removes_them() -> None:
    # ADR-001 layer 3, with the default 5 s lease and 1 s heartbeats (Sprint 2 decisions).
    toxics = f"http://127.0.0.1:{TOXIPROXY_PORT}/proxies/orders-inventory/toxics"
    heartbeat = f"http://127.0.0.1:{WATCHDOG_PORT}/heartbeat"
    httpx.post(heartbeat, timeout=5).raise_for_status()
    httpx.post(
        toxics,
        json={
            "name": "chaosnet-latency-upstream",
            "type": "latency",
            "stream": "upstream",
            "attributes": {"latency": 100},
        },
        timeout=5,
    ).raise_for_status()
    try:
        for _ in range(7):  # longer than the lease: only heartbeats keep the fault alive
            httpx.post(heartbeat, timeout=5).raise_for_status()
            time.sleep(1)
        assert toxics_on("orders-inventory") == ["chaosnet-latency-upstream"]

        stopped = time.monotonic()  # the control plane "dies" here
        while toxics_on("orders-inventory") and time.monotonic() - stopped < 10:
            time.sleep(0.2)
        assert toxics_on("orders-inventory") == []
        assert 4 <= time.monotonic() - stopped < 7
    finally:
        httpx.post(f"http://127.0.0.1:{TOXIPROXY_PORT}/reset", timeout=5)
