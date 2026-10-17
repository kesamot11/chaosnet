"""Experiment lifecycle: the states an experiment moves through (see #50)."""

from enum import StrEnum


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


def transition(current: State, target: State) -> State:
    """Return ``target`` if moving from ``current`` to ``target`` is allowed, else raise.

    The allowed moves are the acceptance criteria of #50.
    """
    raise NotImplementedError
