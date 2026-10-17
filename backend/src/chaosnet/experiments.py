"""Experiment lifecycle: the states an experiment moves through (see #50)."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class State(StrEnum):
    PENDING = "pending"
    BASELINE = "baseline"
    INJECT = "inject"
    RECOVER = "recover"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


class InvalidTransition(Exception):
    """A state change that the lifecycle does not allow."""


ALLOWED = {
    State.PENDING: {State.BASELINE, State.ABORTED},
    State.BASELINE: {State.INJECT, State.ABORTED, State.FAILED},
    State.INJECT: {State.RECOVER, State.FAILED, State.ABORTED},
    State.RECOVER: {State.COMPLETED, State.ABORTED, State.FAILED},
}


def transition(current: State, target: State) -> State:
    """Return ``target`` if moving from ``current`` to ``target`` is allowed, else raise.

    The allowed moves are the acceptance criteria of #50.
    """
    if target not in ALLOWED.get(current, set()):
        raise InvalidTransition(f"{current} -> {target} is not allowed")
    return target


@dataclass(frozen=True)
class Hypothesis:
    max_p95_ms: float  # p95 of *all* requests during inject (failures make users wait too)
    max_error_rate: float  # share of scheduled requests that did not end "ok", 0.0–1.0


@dataclass(frozen=True)
class Verdict:
    passed: bool
    reasons: list[str]  # one line per broken limit, e.g. "p95 1514.3 ms > 500 ms"


def judge(inject: dict[str, Any], hypothesis: Hypothesis) -> Verdict:
    """Compare the load generator summary of the inject phase with the hypothesis.

    ``inject`` is what ``chaosnet.loadgen.summarize`` returns. A limit holds when the
    value is less than or equal to it. See tests/test_experiments.py.
    """
    raise NotImplementedError
