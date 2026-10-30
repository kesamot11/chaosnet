from typing import Any

import pytest
from pydantic import ValidationError

from chaosnet.experiments import (
    FaultSpec,
    Hypothesis,
    InvalidTransition,
    State,
    Verdict,
    judge,
    transition,
)

HAPPY_PATH = [State.PENDING, State.BASELINE, State.INJECT, State.RECOVER, State.COMPLETED]
RUNNING = [State.BASELINE, State.INJECT, State.RECOVER]
FINAL = [State.COMPLETED, State.FAILED, State.ABORTED]


def test_happy_path_is_allowed_step_by_step() -> None:
    for current, target in zip(HAPPY_PATH, HAPPY_PATH[1:], strict=False):
        assert transition(current, target) == target


@pytest.mark.parametrize("running", RUNNING)
@pytest.mark.parametrize("end", [State.FAILED, State.ABORTED])
def test_a_running_phase_can_fail_or_be_aborted(running: State, end: State) -> None:
    assert transition(running, end) == end


def test_pending_can_be_aborted_before_it_starts() -> None:
    assert transition(State.PENDING, State.ABORTED) == State.ABORTED


@pytest.mark.parametrize("final", FINAL)
@pytest.mark.parametrize("target", list(State))
def test_final_states_are_final(final: State, target: State) -> None:
    with pytest.raises(InvalidTransition):
        transition(final, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (State.PENDING, State.INJECT),  # skipping the baseline: nothing to compare with
        (State.BASELINE, State.RECOVER),  # skipping the fault
        (State.INJECT, State.COMPLETED),  # skipping recovery: never checked the fault is gone
        (State.RECOVER, State.INJECT),  # going backwards
        (State.PENDING, State.FAILED),  # nothing ran, so nothing could fail
        (State.INJECT, State.INJECT),  # no-op "transition"
    ],
)
def test_other_transitions_are_rejected(current: State, target: State) -> None:
    with pytest.raises(InvalidTransition):
        transition(current, target)


def test_error_names_both_states() -> None:
    with pytest.raises(InvalidTransition, match=r"inject.*completed"):
        transition(State.INJECT, State.COMPLETED)


# --- #53: hypothesis verdict, with the real EXP-002 numbers ---------------------------

# EXP-002 A, run 1: +300 ms on the request side
EXP002_A = {
    "scheduled": 1500,
    "sent": 1500,
    "outcomes": {"ok": 1500},
    "latency_ms": {
        "ok": {"p50": 306.47, "p95": 311.26, "p99": 312.67, "p100": 315.52},
        "all": {"p50": 306.47, "p95": 311.26, "p99": 312.67, "p100": 315.52},
    },
}
# EXP-002 B, run 1: +300 ms both ways, every request a 504 after 1.5 s
EXP002_B = {
    "scheduled": 1500,
    "sent": 1500,
    "outcomes": {"http_5xx": 1500},
    "latency_ms": {
        "ok": None,
        "all": {"p50": 1509.68, "p95": 1514.32, "p99": 1521.4, "p100": 1527.32},
    },
}
LIMITS = Hypothesis(max_p95_ms=500, max_error_rate=0.01)


def test_exp002_a_passes() -> None:
    assert judge(EXP002_A, LIMITS) == Verdict(passed=True, reasons=[])


def test_exp002_b_fails_on_both_limits() -> None:
    verdict = judge(EXP002_B, LIMITS)
    assert not verdict.passed
    assert len(verdict.reasons) == 2
    assert any("p95" in r and "1514.3" in r and "500" in r for r in verdict.reasons)
    assert any("error rate" in r and "100.0 %" in r and "1.0 %" in r for r in verdict.reasons)


def test_only_the_broken_limit_is_reported() -> None:
    verdict = judge(EXP002_A, Hypothesis(max_p95_ms=300, max_error_rate=0.01))
    assert verdict == Verdict(passed=False, reasons=["p95 311.3 ms > 300 ms"])


def test_a_value_equal_to_the_limit_passes() -> None:
    assert judge(EXP002_A, Hypothesis(max_p95_ms=311.26, max_error_rate=0.0)).passed


def test_dropped_and_failed_requests_count_as_errors() -> None:
    summary = {
        **EXP002_A,
        "sent": 1490,
        "outcomes": {"ok": 1470, "timeout": 20, "dropped": 10},
    }
    verdict = judge(summary, Hypothesis(max_p95_ms=500, max_error_rate=0.01))
    assert verdict.reasons == ["error rate 2.0 % > 1.0 %"]  # 30 of 1500


@pytest.mark.parametrize(
    "data",
    [
        {
            "kind": "latency",
            "link": "orders-inventory",
            "ms": 200,
            "kbps": 150,
        },  # latency, ale s kbps
        {
            "kind": "bandwidth",
            "link": "orders-inventory",
            "kbps": 50,
            "ms": 10,
        },  # bandwidth, ale s ms
        {"kind": "reset_peer", "link": "orders-inventory", "ms": 150},  # reset s ms nebo kbps
    ],
)
def test_a_value_that_does_not_belong_to_the_kind_is_rejected(data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        FaultSpec.model_validate(data)
