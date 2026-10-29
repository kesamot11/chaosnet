"""A generated lab with a branch, run for real (#80): orders calls inventory and payments.

The default lab is a chain, so the branch is generated here into a temporary directory
and started as its own Compose project on its own ports, from the image the default
lab builds.
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
BACKEND_DIR = LAB_DIR.parent / "backend"
PORT, TOXIPROXY_PORT, WATCHDOG_PORT = "28080", "28474", "28475"
TOXIPROXY = f"http://127.0.0.1:{TOXIPROXY_PORT}"
DELAY_MS = 300

TOPOLOGY = {
    "version": 1,
    "services": [
        {"name": "gateway", "port": 8080},
        {"name": "orders"},
        {"name": "inventory"},
        {"name": "payments"},
    ],
    # timeouts well above DELAY_MS: this test measures waiting, not timing out
    "links": [
        {"from": "gateway", "to": "orders", "timeout_s": 3.0},
        {"from": "orders", "to": "inventory", "timeout_s": 2.0},
        {"from": "orders", "to": "payments", "timeout_s": 2.0},
    ],
}


@pytest.fixture(scope="module")
def branch(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    out = tmp_path_factory.mktemp("branch")
    (out / "topology.json").write_text(json.dumps(TOPOLOGY))
    subprocess.run(
        ["uv", "run", "chaosnet-lab", "--topology", out / "topology.json", "--out", out],
        cwd=BACKEND_DIR,
        check=True,
        capture_output=True,
    )
    env = {
        **os.environ,
        "COMPOSE_PROJECT_NAME": "chaosnet-lab-branch",
        "ENTRY_PORT": PORT,
        "TOXIPROXY_PORT": TOXIPROXY_PORT,
        "WATCHDOG_PORT": WATCHDOG_PORT,
        "LEASE_TIMEOUT_S": "600",  # no controller sends heartbeats here; keep the toxics
    }
    # the image is the one the default lab builds; build it if this test runs alone
    subprocess.run(["docker", "compose", "build"], cwd=LAB_DIR, check=True, capture_output=True)
    compose = ["docker", "compose", "-f", str(out / "compose.yaml")]
    subprocess.run([*compose, "up", "-d", "--no-build", "--wait"], env=env, check=True)
    yield out
    subprocess.run([*compose, "down", "--remove-orphans"], env=env, check=True)


def order() -> tuple[httpx.Response, float]:
    start = time.perf_counter()
    res = httpx.post(f"http://127.0.0.1:{PORT}/orders", timeout=10)
    return res, time.perf_counter() - start


def fastest(n: int = 5) -> float:
    return min(order()[1] for _ in range(n))


def test_the_request_goes_down_both_branches(branch: Path) -> None:
    res, _ = order()
    assert res.status_code == 200
    leaf: list[dict[str, object]] = [
        {"service": "inventory", "calls": []},
        {"service": "payments", "calls": []},
    ]
    orders: dict[str, object] = {"service": "orders", "calls": leaf}
    assert res.json() == {"service": "gateway", "calls": [orders]}


def test_both_branches_are_called_at_the_same_time(branch: Path) -> None:
    before = fastest()
    toxic = {"type": "latency", "stream": "downstream", "attributes": {"latency": DELAY_MS}}
    try:
        for link in ("orders-inventory", "orders-payments"):
            url = f"{TOXIPROXY}/proxies/{link}/toxics"
            httpx.post(url, json=toxic, timeout=5).raise_for_status()
        added = fastest() - before
    finally:
        httpx.post(f"{TOXIPROXY}/reset", timeout=5).raise_for_status()
    # one after another would add 2 x 300 ms
    assert DELAY_MS / 1000 * 0.9 <= added < DELAY_MS / 1000 * 1.5, f"added {added:.3f} s"


def test_one_branch_down_fails_the_request_naming_it(branch: Path) -> None:
    compose = ["docker", "compose", "-f", str(branch / "compose.yaml")]
    env = {**os.environ, "COMPOSE_PROJECT_NAME": "chaosnet-lab-branch", "ENTRY_PORT": PORT}
    subprocess.run([*compose, "stop", "payments"], env=env, check=True, capture_output=True)
    try:
        res, _ = order()
        assert res.status_code == 503
        assert res.json() == {"error": "unavailable", "failed_hop": "orders->payments"}
    finally:
        subprocess.run([*compose, "start", "payments"], env=env, check=True, capture_output=True)
