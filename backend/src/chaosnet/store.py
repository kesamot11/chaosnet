"""Experiments on disk (SQLite), so they survive a controller crash (Sprint 3 decision 2).

All access happens on the event loop thread (async API handlers, the runner task), so
one connection is enough and no locking is needed.
"""

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from chaosnet.experiments import State, Verdict, transition

RUNNING = {State.PENDING, State.BASELINE, State.INJECT, State.RECOVER}

SCHEMA = """
CREATE TABLE IF NOT EXISTS experiments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    state      TEXT NOT NULL,
    spec       TEXT NOT NULL,              -- the request body, as JSON
    results    TEXT NOT NULL DEFAULT '{}', -- {phase: load generator summary}, as JSON
    verdict    TEXT,                       -- {"passed": ..., "reasons": [...]}, as JSON
    reason     TEXT,                       -- why it failed or was aborted
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


class ExperimentAlreadyRunning(Exception):
    """Only one experiment may run at a time: there is only one lab (decision 3)."""


@dataclass(frozen=True)
class Experiment:
    id: int
    name: str
    state: State
    spec: dict[str, Any]
    results: dict[str, Any]
    verdict: Verdict | None
    reason: str | None
    created_at: str
    updated_at: str


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class Store:
    def __init__(self, path: str | Path) -> None:
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute(SCHEMA)
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def create(self, name: str, spec: dict[str, Any]) -> Experiment:
        """Store a new ``pending`` experiment, unless another one is still running."""
        running = self.running()
        if running is not None:
            raise ExperimentAlreadyRunning(f"experiment {running.id} is {running.state}")
        ts = now()
        cur = self.db.execute(
            "INSERT INTO experiments (name, state, spec, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (name, State.PENDING, json.dumps(spec), ts, ts),
        )
        self.db.commit()
        assert cur.lastrowid is not None
        return self.get(cur.lastrowid)

    def get(self, experiment_id: int) -> Experiment:
        row = self.db.execute("SELECT * FROM experiments WHERE id = ?", (experiment_id,)).fetchone()
        if row is None:
            raise KeyError(f"no experiment {experiment_id}")
        return to_experiment(row)

    def list(self) -> list[Experiment]:
        rows = self.db.execute("SELECT * FROM experiments ORDER BY id DESC").fetchall()
        return [to_experiment(r) for r in rows]

    def running(self) -> Experiment | None:
        marks = ", ".join("?" * len(RUNNING))
        row = self.db.execute(
            f"SELECT * FROM experiments WHERE state IN ({marks}) ORDER BY id DESC LIMIT 1",
            tuple(RUNNING),
        ).fetchone()
        return None if row is None else to_experiment(row)

    def set_state(self, experiment_id: int, target: State, reason: str | None = None) -> None:
        """Move to ``target``; the lifecycle (``transition``) decides whether that is allowed."""
        current = self.get(experiment_id).state
        transition(current, target)  # raises InvalidTransition
        self._update(experiment_id, state=target, reason=reason)

    def save_result(self, experiment_id: int, phase: State, summary: dict[str, Any]) -> None:
        results = self.get(experiment_id).results
        results[phase] = summary
        self._update(experiment_id, results=json.dumps(results))

    def save_verdict(self, experiment_id: int, verdict: Verdict) -> None:
        payload = {"passed": verdict.passed, "reasons": verdict.reasons}
        self._update(experiment_id, verdict=json.dumps(payload))

    def _update(self, experiment_id: int, **columns: Any) -> None:
        columns["updated_at"] = now()
        assignments = ", ".join(f"{c} = ?" for c in columns)  # column names are ours, not input
        self.db.execute(
            f"UPDATE experiments SET {assignments} WHERE id = ?",
            (*columns.values(), experiment_id),
        )
        self.db.commit()


def to_experiment(row: sqlite3.Row) -> Experiment:
    verdict = json.loads(row["verdict"]) if row["verdict"] else None
    return Experiment(
        id=row["id"],
        name=row["name"],
        state=State(row["state"]),
        spec=json.loads(row["spec"]),
        results=json.loads(row["results"]),
        verdict=None if verdict is None else Verdict(verdict["passed"], verdict["reasons"]),
        reason=row["reason"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
