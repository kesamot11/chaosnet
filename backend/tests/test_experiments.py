import pytest

from chaosnet.experiments import InvalidTransition, State, transition

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
