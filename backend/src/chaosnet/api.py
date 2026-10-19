"""HTTP API of the experiment controller (#54).

    uv run chaosnet-api

Binds to 127.0.0.1 only and has no authentication (ADR-002). The load target is fixed
by configuration, never taken from a request: the API can only send load to the lab.

All handlers are ``async``, so they run on the event loop thread together with the
runner task, which is what the single SQLite connection requires (see store.py).
"""

import asyncio
import os
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException

from chaosnet.experiments import ExperimentSpec, LoadSpec, State
from chaosnet.fault_cli import send_heartbeat
from chaosnet.faults import FaultDriver, FaultError
from chaosnet.loadgen import run_load, summarize
from chaosnet.runner import Runner, reconcile
from chaosnet.store import RUNNING, Experiment, ExperimentAlreadyRunning, Store
from chaosnet.topology import Topology

# Builds the runner for one experiment; the load (rate, body) differs per experiment.
MakeRunner = Callable[[LoadSpec], Runner]


# The lab this controller runs against (#72); CHAOSNET_TOPOLOGY overrides it.
LAB_TOPOLOGY = Path(__file__).parents[3] / "lab" / "topology.json"


def create_app(
    store: Store, make_runner: MakeRunner, topology: Topology, driver: FaultDriver
) -> FastAPI:
    tasks: dict[int, asyncio.Task[None]] = {}
    links = {link.name for link in topology.links}

    async def abort(experiment_id: int) -> None:
        task = tasks.get(experiment_id)
        if task is not None:
            task.cancel()
            await asyncio.wait([task])  # the runner has removed the fault when this returns
        if store.get(experiment_id).state in RUNNING:
            # Cancelled before the task got to run, so the runner never saw it.
            store.set_state(experiment_id, State.ABORTED, reason="aborted by user")

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        yield
        # Stopping the controller ends the experiment and removes its fault (layer 1).
        for experiment_id in list(tasks):
            await abort(experiment_id)

    app = FastAPI(title="ChaosNet", lifespan=lifespan)

    @app.post("/experiments", status_code=201)
    async def start(spec: ExperimentSpec) -> Experiment:
        if spec.fault.link not in links:
            # Found here, not after the baseline was measured (ADR-004 consequences).
            raise HTTPException(
                422, f"unknown link {spec.fault.link!r}, the topology has {sorted(links)}"
            )
        try:
            exp = store.create(spec.name, spec.model_dump())
        except ExperimentAlreadyRunning as e:
            raise HTTPException(409, str(e)) from e
        task = asyncio.create_task(make_runner(spec.load).run(exp.id))
        tasks[exp.id] = task
        task.add_done_callback(lambda _: tasks.pop(exp.id, None))
        return exp

    @app.get("/topology")
    async def get_topology() -> dict[str, Any]:
        try:
            proxies: set[str] = await driver.links()
        except httpx.TransportError, FaultError:
            proxies = set()  # Toxiproxy down: no link can take a fault right now
        result = topology.model_dump(by_alias=True)
        for link, data in zip(topology.links, result["links"], strict=True):
            data |= {"name": link.name, "available": link.name in proxies}
        return result

    @app.get("/experiments")
    async def list_experiments() -> list[Experiment]:
        return store.list()

    @app.get("/experiments/{experiment_id}")
    async def get(experiment_id: int) -> Experiment:
        try:
            return store.get(experiment_id)
        except KeyError as e:
            raise HTTPException(404, f"no experiment {experiment_id}") from e

    @app.post("/experiments/{experiment_id}/abort")
    async def abort_experiment(experiment_id: int) -> Experiment:
        exp = await get(experiment_id)
        if exp.state not in RUNNING:
            raise HTTPException(409, f"experiment {experiment_id} is not running ({exp.state})")
        await abort(experiment_id)
        return store.get(experiment_id)

    return app


async def serve() -> None:
    target = os.environ.get("TARGET_URL", "http://127.0.0.1:8080/orders")
    toxiproxy = os.environ.get("TOXIPROXY_URL", "http://127.0.0.1:8474")
    watchdog = os.environ.get("WATCHDOG_URL", "http://127.0.0.1:8475")
    port = int(os.environ.get("CHAOSNET_PORT", "8476"))
    max_in_flight = 500  # loadgen CLI default

    async with (
        httpx.AsyncClient() as control,
        httpx.AsyncClient(limits=httpx.Limits(max_connections=max_in_flight)) as load_client,
    ):
        with Store(os.environ.get("CHAOSNET_DB", "chaosnet.db")) as store:
            driver = FaultDriver(control, toxiproxy)
            await reconcile(store, driver)  # cleanup layer 2, after a crash (#55)

            async def heartbeat() -> None:
                await send_heartbeat(control, watchdog)

            def make_runner(load: LoadSpec) -> Runner:
                async def measure(seconds: float) -> dict[str, Any]:
                    samples = await run_load(
                        load_client,
                        "POST",
                        target,
                        rate=load.rate,
                        duration_s=seconds,
                        timeout_s=5,
                        max_in_flight=max_in_flight,
                        json_body=load.body,
                    )
                    return summarize(samples, rate=load.rate, duration_s=seconds)

                return Runner(store, driver, measure, heartbeat)

            path = Path(os.environ.get("CHAOSNET_TOPOLOGY", LAB_TOPOLOGY))
            topology = Topology.model_validate_json(path.read_text())
            app = create_app(store, make_runner, topology, driver)
            await uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port)).serve()


def main() -> None:
    asyncio.run(serve())
