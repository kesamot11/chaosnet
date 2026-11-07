import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx
from fakes import API, LINK, FakeToxiproxy, Lab

from chaosnet.api import create_app
from chaosnet.experiments import LoadSpec
from chaosnet.faults import FaultDriver
from chaosnet.lab import Lab as ControlledLab
from chaosnet.lab import LabError
from chaosnet.runner import Runner
from chaosnet.store import Store
from chaosnet.topology import Topology

# The tests' own copy of the default lab: the editor rewrites lab/topology.json (#200).
LAB_TOPOLOGY = Topology.model_validate_json((Path(__file__).parent / "topology.json").read_text())

SPEC: dict[str, Any] = {
    "name": "EXP-003",
    "fault": {"kind": "latency", "link": LINK, "direction": "both", "ms": 300},
    "load": {"rate": 50, "body": {"item_id": "42"}},
    "phases_s": {"baseline": 0.02, "inject": 0.05, "recover": 0.02},
    "hypothesis": {"max_p95_ms": 500, "max_error_rate": 0.01},
}
SLOW = {**SPEC, "phases_s": {"baseline": 0.02, "inject": 5, "recover": 0.02}}

Test = Callable[[httpx.AsyncClient, Lab], Awaitable[None]]


class FakeCompose:
    """``docker compose up`` for tests: waits for ``gate`` if set, then takes the next result.

    A result is None (started) or compose's output (failed); with none left, it starts.
    """

    def __init__(self) -> None:
        self.results: list[str | None] = []
        self.gate: asyncio.Event | None = None

    async def __call__(self, lab_dir: Path) -> None:
        if self.gate is not None:
            await self.gate.wait()
        failure = self.results.pop(0) if self.results else None
        if failure is not None:
            raise LabError(failure)


def run(
    tmp_path: Path,
    test: Test,
    transport: httpx.MockTransport | None = None,
    compose: FakeCompose | None = None,
) -> Lab:
    """Run ``test`` against the API, with fake Toxiproxy, load, watchdog and Docker behind it.

    The lab has started, as after the controller's startup apply (#191).
    """
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

                topology = tmp_path / "topology.json"
                topology.write_text(LAB_TOPOLOGY.model_dump_json(by_alias=True))
                controlled = ControlledLab(topology, compose or FakeCompose())
                await controlled.apply(None)
                app = create_app(store, make_runner, controlled, driver)
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
        # the lab it runs on, so results of different settings can be told apart (#185)
        # every setting of every link: GET adds only the proxy's name and whether it is there
        stored = res.json()["topology"]
        shown = (await client.get("/topology")).json()
        for link in shown["links"]:
            del link["name"], link["available"]
        assert stored == shown

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


# PUT /topology (#190): the default lab plus payments, called by orders.
WITH_PAYMENTS: dict[str, Any] = {
    **LAB_TOPOLOGY.model_dump(by_alias=True),
    "services": [*LAB_TOPOLOGY.model_dump()["services"], {"name": "payments", "port": None}],
    "links": [
        *LAB_TOPOLOGY.model_dump(by_alias=True)["links"],
        {"from": "orders", "to": "payments", "timeout_s": 1.0},
    ],
}


# The same lab as WITH_PAYMENTS: payments only drawn elsewhere, or its link slower.
MOVED_PAYMENTS: dict[str, Any] = {
    **WITH_PAYMENTS,
    "services": [*WITH_PAYMENTS["services"][:-1], {"name": "payments", "x": 300.0, "y": 80.0}],
}
SLOWER_PAYMENTS: dict[str, Any] = {
    **WITH_PAYMENTS,
    "links": [*WITH_PAYMENTS["links"][:-1], {"from": "orders", "to": "payments", "timeout_s": 2.0}],
}


def test_a_saved_topology_is_the_one_used_from_then_on(tmp_path: Path) -> None:
    async def test(client: httpx.AsyncClient, lab: Lab) -> None:
        res = await client.put("/topology", json=WITH_PAYMENTS)
        assert res.status_code == 200
        assert [s["name"] for s in res.json()["services"]] == [
            "gateway",
            "orders",
            "inventory",
            "payments",
        ]
        # on disk, whole, with nothing left beside it
        saved = Topology.model_validate_json((tmp_path / "topology.json").read_text())
        assert [lk.name for lk in saved.links][-1] == "orders-payments"
        assert not (tmp_path / "topology.json.tmp").exists()
        # in memory: GET shows it and an experiment may use the new link
        topo = (await client.get("/topology")).json()
        assert topo["links"][-1]["name"] == "orders-payments"
        await lab_state(client, "running")
        new_link = {**SPEC, "fault": {**SPEC["fault"], "link": "orders-payments"}}
        assert (await client.post("/experiments", json=new_link)).status_code == 201

    run(tmp_path, test)


def test_a_broken_topology_is_refused_and_the_file_kept(tmp_path: Path) -> None:
    async def test(client: httpx.AsyncClient, lab: Lab) -> None:
        before = (tmp_path / "topology.json").read_text()
        cycle = {
            **WITH_PAYMENTS,
            "links": [*WITH_PAYMENTS["links"], {"from": "payments", "to": "orders"}],
        }
        res = await client.put("/topology", json=cycle)
        assert res.status_code == 422
        # FastAPI's shape: a list of errors, `check`'s message after Pydantic's prefix
        [error] = res.json()["detail"]
        assert error["msg"] == "Value error, cycle: gateway -> orders -> payments -> orders"
        assert (tmp_path / "topology.json").read_text() == before

    run(tmp_path, test)


def test_saving_while_an_experiment_runs_is_refused(tmp_path: Path) -> None:
    async def test(client: httpx.AsyncClient, lab: Lab) -> None:
        before = (tmp_path / "topology.json").read_text()
        exp = (await client.post("/experiments", json=SLOW)).json()
        res = await client.put("/topology", json=WITH_PAYMENTS)
        assert res.status_code == 409
        assert f"experiment {exp['id']} is" in res.json()["detail"]
        assert (tmp_path / "topology.json").read_text() == before
        await client.post(f"/experiments/{exp['id']}/abort")

    run(tmp_path, test)


async def lab_state(client: httpx.AsyncClient, state: str) -> dict[str, Any]:
    """Wait until GET /lab says ``state`` (the apply runs in the background)."""
    lab: dict[str, Any] = {}
    for _ in range(500):
        lab = (await client.get("/lab")).json()
        if lab["state"] == state:
            return lab
        await asyncio.sleep(0.01)
    raise AssertionError(f"the lab never reached {state}: {lab}")


def test_a_saved_topology_is_applied_in_the_background(tmp_path: Path) -> None:
    compose = FakeCompose()

    async def test(client: httpx.AsyncClient, lab: Lab) -> None:
        assert (await client.get("/lab")).json() == {"state": "running", "error": None}
        compose.gate = asyncio.Event()
        assert (await client.put("/topology", json=WITH_PAYMENTS)).status_code == 200
        assert (await client.get("/lab")).json()["state"] == "restarting"
        # ADR-011: no second apply, no experiment while the lab restarts
        res = await client.put("/topology", json=SLOWER_PAYMENTS)
        assert (res.status_code, res.json()["detail"]) == (
            409,
            "the lab is restarting, wait until it runs",
        )
        res = await client.post("/experiments", json=SPEC)
        assert (res.status_code, res.json()["detail"]) == (
            409,
            "the lab is restarting, not running",
        )
        compose.gate.set()
        assert await lab_state(client, "running") == {"state": "running", "error": None}
        assert "payments" in (tmp_path / "compose.yaml").read_text()  # regenerated

    run(tmp_path, test, compose=compose)


def test_a_topology_that_fails_to_start_is_rolled_back(tmp_path: Path) -> None:
    compose = FakeCompose()

    async def test(client: httpx.AsyncClient, lab: Lab) -> None:
        before = (tmp_path / "topology.json").read_text()
        compose.results = ["container payments is unhealthy", None]  # the old one starts
        await client.put("/topology", json=WITH_PAYMENTS)
        state = await lab_state(client, "running")
        assert state["error"] == (
            "the new topology failed, the previous one is back: container payments is unhealthy"
        )
        topo = (await client.get("/topology")).json()
        assert [s["name"] for s in topo["services"]] == ["gateway", "orders", "inventory"]
        assert Topology.model_validate_json((tmp_path / "topology.json").read_text()) == (
            Topology.model_validate_json(before)
        )
        assert "payments" not in (tmp_path / "compose.yaml").read_text()

    run(tmp_path, test, compose=compose)


def test_when_going_back_fails_too_the_lab_is_failed(tmp_path: Path) -> None:
    compose = FakeCompose()

    async def test(client: httpx.AsyncClient, lab: Lab) -> None:
        compose.results = ["container payments is unhealthy", "Cannot connect to Docker"]
        await client.put("/topology", json=WITH_PAYMENTS)
        state = await lab_state(client, "failed")
        assert state["error"] == (
            "the new topology failed: container payments is unhealthy; "
            "going back failed too: Cannot connect to Docker"
        )
        res = await client.post("/experiments", json=SPEC)
        assert (res.status_code, res.json()["detail"]) == (409, "the lab is failed, not running")
        # saving is how the user repairs it
        assert (await client.put("/topology", json=WITH_PAYMENTS)).status_code == 200
        assert (await lab_state(client, "running"))["error"] is None

    run(tmp_path, test, compose=compose)


def test_moving_services_saves_them_without_touching_the_lab(tmp_path: Path) -> None:
    # #192 (Tomáš): only positions changed -> saved, not applied; allowed while an
    # experiment runs and while the lab restarts.
    compose = FakeCompose()

    async def test(client: httpx.AsyncClient, lab: Lab) -> None:
        await client.put("/topology", json=WITH_PAYMENTS)
        await lab_state(client, "running")

        exp = (await client.post("/experiments", json=SLOW)).json()
        res = await client.put("/topology", json=MOVED_PAYMENTS)
        assert res.status_code == 200
        assert res.json()["services"][-1] | {"x": 300.0, "y": 80.0} == res.json()["services"][-1]
        assert (await client.get("/lab")).json()["state"] == "running"  # not applied
        saved = Topology.model_validate_json((tmp_path / "topology.json").read_text())
        assert (saved.services[-1].x, saved.services[-1].y) == (300.0, 80.0)
        res = await client.put("/topology", json=SLOWER_PAYMENTS)
        assert res.status_code == 409  # a change of the lab still waits for the experiment
        await client.post(f"/experiments/{exp['id']}/abort")

        compose.gate = asyncio.Event()
        await client.put("/topology", json=WITH_PAYMENTS)  # positions back: still not applied
        await client.put("/topology", json=SLOWER_PAYMENTS)  # applied: restarting
        assert (await client.get("/lab")).json()["state"] == "restarting"
        moved = {**SLOWER_PAYMENTS, "services": MOVED_PAYMENTS["services"]}
        assert (await client.put("/topology", json=moved)).status_code == 200  # only moved
        assert (await client.put("/topology", json=MOVED_PAYMENTS)).status_code == 409  # lab
        assert (await client.get("/lab")).json()["state"] == "restarting"
        compose.gate.set()
        await lab_state(client, "running")

    run(tmp_path, test, compose=compose)
