"""A phase that schedules no request is rejected before anything runs (#98)."""

from typing import Any

import pytest
from pydantic import ValidationError

from chaosnet.experiments import ExperimentSpec


def spec(
    rate: float, baseline: float = 10, inject: float = 10, recover: float = 10
) -> dict[str, Any]:
    return {
        "name": "x",
        "fault": {"kind": "latency", "link": "orders-inventory", "ms": 200},
        "load": {"rate": rate},
        "phases_s": {"baseline": baseline, "inject": inject, "recover": recover},
        "hypothesis": {"max_p95_ms": 500, "max_error_rate": 0.01},
    }


@pytest.mark.parametrize(
    ("phase", "data"),
    [
        ("baseline", spec(0.5, baseline=1)),
        ("inject", spec(0.5, inject=1)),  # the sum of all phases would still be 10.5
        ("recover", spec(0.5, recover=1)),
    ],
)
def test_a_phase_without_a_request_is_rejected_by_name(phase: str, data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match=phase):
        ExperimentSpec.model_validate(data)


def test_one_request_per_phase_is_enough() -> None:
    ExperimentSpec.model_validate(spec(1, baseline=1, inject=1, recover=1))
