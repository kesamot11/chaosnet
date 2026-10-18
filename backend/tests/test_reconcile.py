import asyncio
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fakes import API, LINK, FakeToxiproxy

from chaosnet.experiments import State
from chaosnet.faults import FaultDriver
from chaosnet.runner import reconcile
from chaosnet.store import Store

SPEC = {"name": "x"}
PHASES = [State.BASELINE, State.INJECT, State.RECOVER]


def crash_during(store: Store, phase: State) -> int:
    """An experiment whose controller died with it in ``phase`` (no cleanup ran)."""
    exp = store.create("crashed", SPEC)
    if phase != State.PENDING:
        for state in PHASES[: PHASES.index(phase) + 1]:
            store.set_state(exp.id, state)
    return exp.id


def restart(store: Store, toxiproxy: FakeToxiproxy | None) -> None:
    """Run reconcile as the controller does on startup; ``None`` = Toxiproxy is down."""

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    async def go() -> None:
        handler = down if toxiproxy is None else toxiproxy.handle
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await reconcile(store, FaultDriver(client, API))

    asyncio.run(go())


@pytest.fixture
def store(tmp_path: Path) -> Iterator[Store]:
    with Store(tmp_path / "chaosnet.db") as s:
        yield s


@pytest.mark.parametrize("phase", [State.PENDING, *PHASES])
def test_interrupted_experiment_is_aborted_with_its_phase(store: Store, phase: State) -> None:
    experiment_id = crash_during(store, phase)
    restart(store, FakeToxiproxy())
    exp = store.get(experiment_id)
    assert (exp.state, exp.reason) == (State.ABORTED, f"controller restarted during {phase}")
    assert store.running() is None  # the lab is free for the next experiment


def test_leftover_faults_are_removed(store: Store) -> None:
    crash_during(store, State.INJECT)
    toxiproxy = FakeToxiproxy()
    toxiproxy.toxics[LINK] = [{"name": "chaosnet-latency-upstream", "type": "latency"}]
    restart(store, toxiproxy)
    assert toxiproxy.toxics[LINK] == []


def test_finished_experiments_are_left_alone(store: Store) -> None:
    done = store.create("done", SPEC)
    for state in [State.BASELINE, State.INJECT, State.RECOVER, State.COMPLETED]:
        store.set_state(done.id, state)
    failed = store.create("failed", SPEC)
    store.set_state(failed.id, State.BASELINE)
    store.set_state(failed.id, State.FAILED, reason="RuntimeError: boom")

    restart(store, FakeToxiproxy())
    assert store.get(done.id).state == State.COMPLETED
    assert (store.get(failed.id).state, store.get(failed.id).reason) == (
        State.FAILED,
        "RuntimeError: boom",
    )


def test_toxiproxy_down_does_not_stop_the_records_from_being_fixed(store: Store) -> None:
    # A stopped Toxiproxy holds no toxics (they live in its memory), so there is
    # nothing to remove; the records must still be fixed and the controller must start.
    experiment_id = crash_during(store, State.INJECT)
    restart(store, None)
    assert store.get(experiment_id).state == State.ABORTED


def test_clean_start_does_nothing_harmful(store: Store) -> None:
    restart(store, FakeToxiproxy())
    assert store.list() == []
