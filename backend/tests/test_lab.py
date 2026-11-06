import asyncio
import os
import shutil
import stat
from pathlib import Path

import pytest

from chaosnet.lab import Lab, LabError, compose_up

# A `docker` on PATH that records its arguments and fails when told to.
FAKE_DOCKER = """#!/bin/sh
echo "$PWD $*" >> "$CALLS"
if [ -n "$FAIL" ]; then echo "$FAIL"; exit 1; fi
"""


@pytest.fixture
def docker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "docker").write_text(FAKE_DOCKER)
    (bin_dir / "docker").chmod(stat.S_IRWXU)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("CALLS", str(tmp_path / "calls"))
    monkeypatch.delenv("FAIL", raising=False)
    return tmp_path / "calls"


def test_compose_up_recreates_toxiproxy_and_prometheus_then_starts_the_rest(
    docker: Path, tmp_path: Path
) -> None:
    asyncio.run(compose_up(tmp_path))
    assert docker.read_text().splitlines() == [
        f"{tmp_path} compose up -d --wait --wait-timeout 30 "
        "--force-recreate --no-deps toxiproxy prometheus",
        f"{tmp_path} compose up -d --wait --wait-timeout 30 --remove-orphans",
    ]


def test_compose_up_fails_with_compose_output(
    docker: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAIL", "container payments is unhealthy")
    with pytest.raises(LabError, match="^container payments is unhealthy$"):
        asyncio.run(compose_up(tmp_path))
    assert len(docker.read_text().splitlines()) == 1  # stopped at the first failure


def test_a_lab_that_fails_at_controller_start_is_failed(tmp_path: Path) -> None:
    # Controller start (#191): apply the file with nothing to go back to.
    topology = tmp_path / "topology.json"
    shutil.copy(Path(__file__).parents[2] / "lab" / "topology.json", topology)

    async def compose(lab_dir: Path) -> None:
        raise LabError("Cannot connect to the Docker daemon")

    lab = Lab(topology, compose)
    asyncio.run(lab.apply(None))
    assert (lab.state, lab.error) == ("failed", "Cannot connect to the Docker daemon")
    assert (tmp_path / "compose.yaml").exists()  # generated from the file before starting
