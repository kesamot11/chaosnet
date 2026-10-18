import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakes import API, LINK, FakeToxiproxy, Lab

from chaosnet.experiments import State
from chaosnet.faults import FaultDriver
from chaosnet.runner import Runner
from chaosnet.store import Store

SPEC: dict[str, Any] = {
    "name": "EXP-002 A",
    "fault": {"kind": "latency", "link": LINK, "direction": "both", "ms": 300},
    "load": {"rate": 50, "body": {"item_id": "42"}},
    "phases_s": {"baseline": 0.03, "inject": 0.1, "recover": 0.03},
    "hypothesis": {"max_p95_ms": 500, "max_error_rate": 0.01},
}


@pytest.fixture
def store(tmp_path: Path) -> Iterator[Store]:
    with Store(tmp_path / "chaosnet.db") as s:
        yield s


def run(
    store: Store, lab: Lab, spec: dict[str, Any] = SPEC, abort_after_s: float | None = None
) -> int:
    exp = store.create(spec["name"], spec)

    async def go() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lab.toxiproxy.handle)) as c:
            runner = Runner(
                store, FaultDriver(c, API), lab.measure, lab.heartbeat, heartbeat_interval_s=0.01
            )
            task = asyncio.create_task(runner.run(exp.id))
            if abort_after_s is not None:
                await asyncio.sleep(abort_after_s)
                task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    asyncio.run(go())
    return exp.id


def test_happy_path_runs_three_phases_and_completes(store: Store) -> None:
    lab = Lab(FakeToxiproxy())
    exp = store.get(run(store, lab))
    assert exp.state == State.COMPLETED
    assert set(exp.results) == {"baseline", "inject", "recover"}
    assert exp.verdict is not None and exp.verdict.passed
    assert [seconds for seconds, _, _ in lab.measured] == [0.03, 0.1, 0.03]


def test_fault_is_active_exactly_during_the_inject_measurement(store: Store) -> None:
    lab = Lab(FakeToxiproxy())
    run(store, lab)
    # (toxics at start, toxics at end) per phase; "both" = 2 toxics
    assert [(start, end) for _, start, end in lab.measured] == [(0, 0), (2, 2), (0, 0)]
    assert lab.toxiproxy.toxics[LINK] == []


def test_heartbeats_while_the_fault_is_active_and_not_after(store: Store) -> None:
    lab = Lab(FakeToxiproxy())
    run(store, lab)
    assert lab.heartbeats >= 3  # 0.1 s inject / 0.01 s interval
    beats_after_inject = lab.heartbeats

    async def wait() -> None:
        await asyncio.sleep(0.05)

    asyncio.run(wait())
    assert lab.heartbeats == beats_after_inject


def test_error_during_inject_fails_the_experiment_and_removes_the_fault(store: Store) -> None:
    lab = Lab(FakeToxiproxy(), fail_in_phase=1)
    exp = store.get(run(store, lab))
    assert exp.state == State.FAILED
    assert exp.reason == "RuntimeError: load generator crashed"
    assert lab.toxiproxy.toxics[LINK] == []


def test_abort_during_inject_removes_the_fault(store: Store) -> None:
    lab = Lab(FakeToxiproxy())
    spec = {**SPEC, "phases_s": {"baseline": 0.01, "inject": 5, "recover": 0.01}}
    exp = store.get(run(store, lab, spec, abort_after_s=0.1))
    assert (exp.state, exp.reason) == (State.ABORTED, "aborted by user")
    assert lab.toxiproxy.toxics[LINK] == []


def test_fault_that_cannot_be_added_fails_the_experiment(store: Store) -> None:
    lab = Lab(FakeToxiproxy())
    spec = {**SPEC, "fault": {**SPEC["fault"], "link": "no-such-link"}}
    exp = store.get(run(store, lab, spec))
    assert exp.state == State.FAILED
    assert exp.reason is not None and "no-such-link" in exp.reason
    assert len(lab.measured) == 1  # only the baseline was measured


def test_error_in_baseline_never_adds_a_fault(store: Store) -> None:
    lab = Lab(FakeToxiproxy(), fail_in_phase=0)
    exp = store.get(run(store, lab))
    assert exp.state == State.FAILED
    assert lab.toxiproxy.requests == []  # Toxiproxy was never called
