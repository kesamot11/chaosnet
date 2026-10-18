"""Experiment lifecycle: the states an experiment moves through (see #50)."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from chaosnet.faults import Direction


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
    reasons: list[str] = []
    ok_number = inject["outcomes"].get("ok", 0)
    p95 = inject["latency_ms"]["all"]["p95"]
    err_rate = (inject["scheduled"] - ok_number) / inject["scheduled"]
    if p95 > hypothesis.max_p95_ms:
        reasons.append(f"p95 {p95:.1f} ms > {hypothesis.max_p95_ms:g} ms")
    if err_rate > hypothesis.max_error_rate:
        reasons.append(
            f"error rate {(err_rate * 100):.1f} % > {(hypothesis.max_error_rate * 100):.1f} %"
        )
    return Verdict(len(reasons) == 0, reasons)


# --- the experiment definition: the body of POST /experiments (Sprint 3 decision 5) ----


class FaultSpec(BaseModel):
    kind: Literal["latency", "bandwidth", "reset_peer"]
    link: str
    direction: Direction = "both"
    ms: int | None = Field(default=None, gt=0)  # latency
    kbps: int | None = Field(default=None, gt=0)  # bandwidth

    @model_validator(mode="after")
    def value_matches_kind(self) -> FaultSpec:
        if self.kind == "latency" and self.ms is None:
            raise ValueError("a latency fault needs ms")
        if self.kind == "bandwidth" and self.kbps is None:
            raise ValueError("a bandwidth fault needs kbps")
        return self


class LoadSpec(BaseModel):
    rate: float = Field(gt=0)  # requests per second, open model
    body: dict[str, Any] = {}


class PhasesSpec(BaseModel):
    baseline: float = Field(gt=0)  # seconds
    inject: float = Field(gt=0)
    recover: float = Field(gt=0)


class ExperimentSpec(BaseModel):
    name: str
    fault: FaultSpec
    load: LoadSpec
    phases_s: PhasesSpec
    hypothesis: Hypothesis
