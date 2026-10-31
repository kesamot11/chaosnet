"""A circuit breaker on orders -> inventory, run for real (#136, ADR-008).

The default lab has no breaker, so this lab is generated into a temporary directory and
run as its own Compose project on its own ports, like test_branching.py.
"""

import json
import os
import subprocess
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.integration

LAB_DIR = Path(__file__).parents[2]
BACKEND_DIR = LAB_DIR.parent / "backend"
PORT = "38080"
ENV = {
    **os.environ,
    "COMPOSE_PROJECT_NAME": "chaosnet-lab-breaker",
    "ENTRY_PORT": PORT,
    "TOXIPROXY_PORT": "38474",
    "WATCHDOG_PORT": "38475",
    "PROMETHEUS_PORT": "39090",
    "LEASE_TIMEOUT_S": "600",
}
TOPOLOGY = {
    "version": 1,
    "services": [{"name": "gateway", "port": 8080}, {"name": "orders"}, {"name": "inventory"}],
    "links": [
        {"from": "gateway", "to": "orders", "timeout_s": 2.0, "max_retries": 1},
        {"from": "orders", "to": "inventory", "timeout_s": 0.5, "max_retries": 2, "breaker": True},
    ],
}


@pytest.fixture(scope="module")
def lab(tmp_path_factory: pytest.TempPathFactory) -> Iterator[list[str]]:
    out = tmp_path_factory.mktemp("breaker")
    (out / "topology.json").write_text(json.dumps(TOPOLOGY))
    subprocess.run(
        ["uv", "run", "chaosnet-lab", "--topology", out / "topology.json", "--out", out],
        cwd=BACKEND_DIR,
        check=True,
        capture_output=True,
    )
    subprocess.run(["docker", "compose", "build"], cwd=LAB_DIR, check=True, capture_output=True)
    compose = ["docker", "compose", "-f", str(out / "compose.yaml")]
    subprocess.run([*compose, "up", "-d", "--no-build", "--wait"], env=ENV, check=True)
    yield compose
    subprocess.run([*compose, "down", "--remove-orphans"], env=ENV, check=True)


def order() -> tuple[httpx.Response, float]:
    start = time.perf_counter()
    res = httpx.post(f"http://127.0.0.1:{PORT}/orders", timeout=10)
    return res, time.perf_counter() - start


def test_the_breaker_opens_fails_fast_and_closes_after_recovery(lab: list[str]) -> None:
    def run(*args: str) -> None:
        subprocess.run([*lab, *args], env=ENV, check=True, capture_output=True)

    run("pause", "inventory")
    try:
        # 10 at once: one after another, each 1.5 s, only ~7 would fit in the 10 s window
        with ThreadPoolExecutor(10) as pool:
            first = [f.result() for f in [pool.submit(order) for _ in range(10)]]
        assert [r.status_code for r, _ in first] == [504] * 10

        res, elapsed = order()
        assert res.status_code == 503
        assert res.json() == {"error": "circuit_open", "failed_hop": "orders->inventory"}
        assert elapsed < 0.2, "an open breaker answers without waiting for a timeout"
    finally:
        run("unpause", "inventory")

    time.sleep(5.5)  # the cooldown; then the next call is the trial
    res, _ = order()
    assert res.status_code == 200
    res, _ = order()
    assert res.status_code == 200  # closed again
