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
from chaosnet.lab import Lab, compose_up, save
from chaosnet.loadgen import run_load, summarize
from chaosnet.runner import Runner, reconcile
from chaosnet.store import RUNNING, Experiment, ExperimentAlreadyRunning, Store
from chaosnet.topology import Topology, same_lab

# Builds the runner for one experiment; the load (rate, body) differs per experiment.
MakeRunner = Callable[[LoadSpec], Runner]


# The lab this controller runs against (#72); CHAOSNET_TOPOLOGY overrides it.
LAB_TOPOLOGY = Path(__file__).parents[3] / "lab" / "topology.json"


def create_app(store: Store, make_runner: MakeRunner, lab: Lab, driver: FaultDriver) -> FastAPI:
    """``lab`` holds the topology in effect and whether the lab runs (#190, #191)."""
    tasks: dict[int, asyncio.Task[None]] = {}
    applying: set[asyncio.Task[None]] = set()  # kept, or the event loop may drop the task

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
        if lab.state != "running":  # ADR-011, decision 5
            raise HTTPException(409, f"the lab is {lab.state}, not running")
        links = {link.name for link in lab.topology.links}
        if spec.fault.link not in links:
            # Found here, not after the baseline was measured (ADR-004 consequences).
            raise HTTPException(
                422, f"unknown link {spec.fault.link!r}, the topology has {sorted(links)}"
            )
        try:
            # the lab runs this topology now (the check above), so results can name their settings
            exp = store.create(spec.name, spec.model_dump(), lab.topology.model_dump(by_alias=True))
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
        result = lab.topology.model_dump(by_alias=True)
        for link, data in zip(lab.topology.links, result["links"], strict=True):
            data |= {"name": link.name, "available": link.name in proxies}
        return result

    @app.put("/topology")
    async def put_topology(new: Topology) -> dict[str, Any]:
        """Save a topology from the editor (#190); a broken one never gets here (422)."""
        only_positions = same_lab(new, lab.topology)  # True: the lab doesn't change (#192)
        running = store.running()
        if running and not only_positions:
            raise HTTPException(
                409, f"experiment {running.id} is {running.state}, wait until it ends"
            )
        # two applies at once would overwrite each other
        if lab.state == "restarting" and not only_positions:
            raise HTTPException(409, "the lab is restarting, wait until it runs")
        previous = lab.topology
        save(new, lab.path)
        lab.topology = new
        if only_positions:
            return await get_topology()  # nothing for the lab to apply
        lab.state = "restarting"  # now, not when the task starts: refuse the next request
        task = asyncio.create_task(lab.apply(previous))
        applying.add(task)
        task.add_done_callback(applying.discard)
        return await get_topology()

    @app.get("/lab")
    async def get_lab() -> dict[str, str | None]:
        """Whether the lab runs (#191); the UI polls it after a save."""
        return {"state": lab.state, "error": lab.error}

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
            lab = Lab(path, compose_up)
            app = create_app(store, make_runner, lab, driver)
            # The file is the truth: bring the lab to it, also after a crash mid-apply (#191).
            startup = asyncio.create_task(lab.apply(None))
            await uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port)).serve()
            startup.cancel()


def main() -> None:
    asyncio.run(serve())
