import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx
from fakes import API, LINK, FakeToxiproxy, Lab

from chaosnet.api import create_app
from chaosnet.experiments import LoadSpec
from chaosnet.faults import FaultDriver
from chaosnet.runner import Runner
from chaosnet.store import Store
from chaosnet.topology import Topology

LAB_TOPOLOGY = Topology.model_validate_json(
    (Path(__file__).parents[2] / "lab" / "topology.json").read_text()
)

SPEC: dict[str, Any] = {
    "name": "EXP-003",
    "fault": {"kind": "latency", "link": LINK, "direction": "both", "ms": 300},
    "load": {"rate": 50, "body": {"item_id": "42"}},
    "phases_s": {"baseline": 0.02, "inject": 0.05, "recover": 0.02},
    "hypothesis": {"max_p95_ms": 500, "max_error_rate": 0.01},
}
SLOW = {**SPEC, "phases_s": {"baseline": 0.02, "inject": 5, "recover": 0.02}}

Test = Callable[[httpx.AsyncClient, Lab], Awaitable[None]]


def run(tmp_path: Path, test: Test, transport: httpx.MockTransport | None = None) -> Lab:
    """Run ``test`` against the API, with fake Toxiproxy, load and watchdog behind it."""
    lab = Lab(FakeToxiproxy())

    async def go() -> None:
        toxiproxy_transport = transport or httpx.MockTransport(lab.toxiproxy.handle)
        with Store(tmp_path / "chaosnet.db") as store:
            async with httpx.AsyncClient(transport=toxiproxy_transport) as toxiproxy:
                driver = FaultDriver(toxiproxy, API)

                def make_runner(_: LoadSpec) -> Runner:
                    return Runner(
                        store, driver, lab.measure, lab.heartbeat, heartbeat_interval_s=0.01
                    )

                app = create_app(store, make_runner, LAB_TOPOLOGY, driver)
                api = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=api, base_url="http://api") as client:
                    await test(client, lab)

    asyncio.run(go())
    return lab


async def wait_for(client: httpx.AsyncClient, experiment_id: int, state: str) -> dict[str, Any]:
    exp: dict[str, Any] = {}
    for _ in range(500):
        exp = (await client.get(f"/experiments/{experiment_id}")).json()
        if exp["state"] == state:
            return exp
        await asyncio.sleep(0.01)
    raise AssertionError(f"experiment {experiment_id} never reached {state}: {exp}")


def test_experiment_runs_to_completion(tmp_path: Path) -> None:
    async def test(client: httpx.AsyncClient, lab: Lab) -> None:
        res = await client.post("/experiments", json=SPEC)
        assert res.status_code == 201
        assert res.json()["state"] == "pending"

        exp = await wait_for(client, res.json()["id"], "completed")
        assert set(exp["results"]) == {"baseline", "inject", "recover"}
        assert exp["verdict"] == {"passed": True, "reasons": []}

    run(tmp_path, test)


def test_invalid_body_is_rejected(tmp_path: Path) -> None:
    async def test(client: httpx.AsyncClient, lab: Lab) -> None:
        no_ms = {**SPEC, "fault": {"kind": "latency", "link": LINK}}
        assert (await client.post("/experiments", json=no_ms)).status_code == 422
        assert (await client.get("/experiments")).json() == []

    run(tmp_path, test)


def test_second_experiment_is_refused_while_one_runs(tmp_path: Path) -> None:
    async def test(client: httpx.AsyncClient, lab: Lab) -> None:
        first = (await client.post("/experiments", json=SLOW)).json()
        res = await client.post("/experiments", json=SPEC)
        assert res.status_code == 409
        assert f"experiment {first['id']}" in res.json()["detail"]
        await client.post(f"/experiments/{first['id']}/abort")

    run(tmp_path, test)


def test_abort_ends_the_experiment_and_removes_the_fault(tmp_path: Path) -> None:
    async def test(client: httpx.AsyncClient, lab: Lab) -> None:
        exp = (await client.post("/experiments", json=SLOW)).json()
        await wait_for(client, exp["id"], "inject")
        assert len(lab.toxiproxy.toxics[LINK]) == 2  # "both" = one toxic per direction

        res = await client.post(f"/experiments/{exp['id']}/abort")
        assert res.status_code == 200
        assert (res.json()["state"], res.json()["reason"]) == ("aborted", "aborted by user")
        assert lab.toxiproxy.toxics[LINK] == []  # removed before the response was sent

        # The lab is free again.
        assert (await client.post("/experiments", json=SPEC)).status_code == 201

    run(tmp_path, test)


def test_abort_right_after_start(tmp_path: Path) -> None:
    async def test(client: httpx.AsyncClient, lab: Lab) -> None:
        # The runner task has not started yet when the abort arrives.
        exp = (await client.post("/experiments", json=SLOW)).json()
        res = await client.post(f"/experiments/{exp['id']}/abort")
        assert res.json()["state"] == "aborted"

    run(tmp_path, test)


def test_failed_experiment_shows_why_and_frees_the_lab(tmp_path: Path) -> None:
    async def test(client: httpx.AsyncClient, lab: Lab) -> None:
        del lab.toxiproxy.toxics[LINK]  # in the topology, but its proxy is gone
        exp = await wait_for(
            client, (await client.post("/experiments", json=SPEC)).json()["id"], "failed"
        )
        assert LINK in exp["reason"]
        assert (await client.post(f"/experiments/{exp['id']}/abort")).status_code == 409
        assert (await client.post("/experiments", json=SPEC)).status_code == 201

    run(tmp_path, test)


def test_abort_of_a_finished_experiment_is_refused(tmp_path: Path) -> None:
    async def test(client: httpx.AsyncClient, lab: Lab) -> None:
        exp = (await client.post("/experiments", json=SPEC)).json()
        await wait_for(client, exp["id"], "completed")
        res = await client.post(f"/experiments/{exp['id']}/abort")
        assert res.status_code == 409
        assert "not running (completed)" in res.json()["detail"]

    run(tmp_path, test)


def test_list_and_unknown_experiment(tmp_path: Path) -> None:
    async def test(client: httpx.AsyncClient, lab: Lab) -> None:
        first = (await client.post("/experiments", json=SPEC)).json()
        await wait_for(client, first["id"], "completed")
        second = (await client.post("/experiments", json=SPEC)).json()
        await wait_for(client, second["id"], "completed")

        listed = (await client.get("/experiments")).json()
        assert [e["id"] for e in listed] == [second["id"], first["id"]]  # newest first

        res = await client.get("/experiments/42")
        assert (res.status_code, res.json()["detail"]) == (404, "no experiment 42")

    run(tmp_path, test)


def test_topology_says_which_links_can_take_a_fault(tmp_path: Path) -> None:
    async def test(client: httpx.AsyncClient, lab: Lab) -> None:
        del lab.toxiproxy.toxics["gateway-orders"]  # proxy missing in Toxiproxy
        topo = (await client.get("/topology")).json()
        assert [s["name"] for s in topo["services"]] == ["gateway", "orders", "inventory"]
        assert [(lk["from"], lk["to"], lk["name"], lk["available"]) for lk in topo["links"]] == [
            ("gateway", "orders", "gateway-orders", False),
            ("orders", "inventory", "orders-inventory", True),
        ]

    run(tmp_path, test)


def test_topology_with_toxiproxy_down(tmp_path: Path) -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    async def test(client: httpx.AsyncClient, lab: Lab) -> None:
        topo = (await client.get("/topology")).json()
        assert [lk["available"] for lk in topo["links"]] == [False, False]

    run(tmp_path, test, transport=httpx.MockTransport(down))


def test_experiment_on_a_link_outside_the_topology_is_rejected(tmp_path: Path) -> None:
    async def test(client: httpx.AsyncClient, lab: Lab) -> None:
        bad = {**SPEC, "fault": {**SPEC["fault"], "link": "orders-payments"}}
        res = await client.post("/experiments", json=bad)
        assert res.status_code == 422
        assert "orders-payments" in res.json()["detail"]
        assert (await client.get("/experiments")).json() == []  # nothing was stored

    run(tmp_path, test)
