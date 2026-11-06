"""The running lab: applying a topology to it (#191, ADR-011).

The controller saves a topology (#190), regenerates the lab from it (``write_lab``) and
starts it with ``docker compose``. The command is fixed; nothing from a request goes into
it, and service names are only ``[a-z0-9]+`` (``check``), so nothing else can reach
``compose.yaml``.
"""

import asyncio
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Literal

from chaosnet.labgen import write_lab
from chaosnet.topology import Topology

LabState = Literal["running", "restarting", "failed"]

# Until every service is healthy. Measured 6.5-7.9 s for today's 7 containers
# (2026-11-06, --force-recreate); larger topologies start longer (depends_on).
WAIT_S = 30


class LabError(Exception):
    """``docker compose`` failed; the message is its output."""


# Starts the lab generated in a directory; raises LabError. A fake in tests.
Compose = Callable[[Path], Awaitable[None]]


async def compose_up(lab_dir: Path) -> None:
    """Start the lab generated in ``lab_dir`` and wait until every service is healthy.

    Toxiproxy and Prometheus read their files only when they start, and compose doesn't
    see a changed file, only a changed ``compose.yaml``: they are always recreated
    (#191, decided by Tomáš). Containers of removed services are removed.
    """
    for args in (
        ["--force-recreate", "--no-deps", "toxiproxy", "prometheus"],
        ["--remove-orphans"],
    ):
        process = await asyncio.create_subprocess_exec(
            *("docker", "compose", "up", "-d", "--wait", "--wait-timeout", str(WAIT_S)),
            *args,
            cwd=lab_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,  # one text for the error, in order
        )
        output, _ = await process.communicate()
        if process.returncode != 0:
            raise LabError(output.decode(errors="replace").strip())


def save(topology: Topology, path: Path) -> None:
    """Write ``topology`` to ``path``; a crash leaves the old file or the new one (#190)."""
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(topology.model_dump_json(by_alias=True, indent=2))
    os.replace(tmp, path)


class Lab:
    """The lab as the API sees it (#191): the topology in effect and whether it runs."""

    def __init__(self, topology_path: Path, compose: Compose) -> None:
        self.path = topology_path
        self.compose = compose
        self.topology = Topology.model_validate_json(topology_path.read_text())
        self.state: LabState = "restarting"
        self.error: str | None = None

    async def apply(self, previous: Topology | None) -> None:
        """Bring the lab to ``self.topology``, already saved in ``self.path`` (ADR-011).

        On failure go back to ``previous``; None at controller start, with nothing to go back to.
        """
        self.state = "restarting"
        self.error = None
        try:
            await self._start()
            self.state = "running"
            return
        except LabError as e:
            first = str(e)
        if previous is None:
            self.state = "failed"
            self.error = first
            return
        self.topology = previous
        save(previous, self.path)
        try:
            await self._start()
            self.state = "running"
            self.error = f"the new topology failed, the previous one is back: {first}"
        except LabError as e:
            self.state = "failed"
            self.error = f"the new topology failed: {first}; going back failed too: {e}"

    async def _start(self) -> None:
        write_lab(self.path, self.path.parent)
        await self.compose(self.path.parent)
