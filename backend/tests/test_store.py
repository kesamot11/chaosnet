from pathlib import Path

import pytest

from chaosnet.experiments import InvalidTransition, State, Verdict
from chaosnet.store import ExperimentAlreadyRunning, Store

SPEC = {"name": "EXP-002 A", "fault": {"kind": "latency", "ms": 300}}


def finish(store: Store, experiment_id: int) -> None:
    for state in (State.BASELINE, State.INJECT, State.RECOVER, State.COMPLETED):
        store.set_state(experiment_id, state)


def test_new_experiment_is_pending(tmp_path: Path) -> None:
    exp = Store(tmp_path / "chaosnet.db").create("EXP-002 A", SPEC)
    assert (exp.id, exp.state, exp.spec, exp.results, exp.verdict) == (
        1,
        State.PENDING,
        SPEC,
        {},
        None,
    )


def test_everything_survives_reopening_the_database(tmp_path: Path) -> None:
    # Reopening the file is what happens after a controller crash and restart.
    db = tmp_path / "chaosnet.db"
    store = Store(db)
    exp = store.create("EXP-002 A", SPEC)
    store.set_state(exp.id, State.BASELINE)
    store.save_result(exp.id, State.BASELINE, {"latency_ms": {"all": {"p95": 11.1}}})
    store.set_state(exp.id, State.INJECT)

    reopened = Store(db).get(exp.id)
    assert reopened.state == State.INJECT
    assert reopened.results == {"baseline": {"latency_ms": {"all": {"p95": 11.1}}}}


def test_state_changes_follow_the_lifecycle(tmp_path: Path) -> None:
    store = Store(tmp_path / "chaosnet.db")
    exp = store.create("x", SPEC)
    with pytest.raises(InvalidTransition):
        store.set_state(exp.id, State.COMPLETED)  # skipping every phase
    assert store.get(exp.id).state == State.PENDING  # nothing was written


def test_only_one_experiment_runs_at_a_time(tmp_path: Path) -> None:
    store = Store(tmp_path / "chaosnet.db")
    first = store.create("first", SPEC)
    with pytest.raises(ExperimentAlreadyRunning, match=f"experiment {first.id}"):
        store.create("second", SPEC)
    finish(store, first.id)
    assert store.create("second", SPEC).id == 2  # allowed once the first one ended


def test_running_finds_the_active_experiment(tmp_path: Path) -> None:
    store = Store(tmp_path / "chaosnet.db")
    assert store.running() is None
    exp = store.create("x", SPEC)
    store.set_state(exp.id, State.BASELINE)
    running = store.running()
    assert running is not None and running.id == exp.id
    store.set_state(exp.id, State.ABORTED, reason="stopped by user")
    assert store.running() is None
    assert store.get(exp.id).reason == "stopped by user"


def test_list_is_newest_first_and_verdict_is_stored(tmp_path: Path) -> None:
    store = Store(tmp_path / "chaosnet.db")
    a = store.create("a", SPEC)
    finish(store, a.id)
    store.save_verdict(a.id, Verdict(passed=False, reasons=["p95 1514.3 ms > 500 ms"]))
    b = store.create("b", SPEC)
    assert [e.name for e in store.list()] == ["b", "a"]
    assert store.get(a.id).verdict == Verdict(False, ["p95 1514.3 ms > 500 ms"])
    assert store.get(b.id).verdict is None


def test_unknown_experiment(tmp_path: Path) -> None:
    with pytest.raises(KeyError, match="no experiment 42"):
        Store(tmp_path / "chaosnet.db").get(42)
