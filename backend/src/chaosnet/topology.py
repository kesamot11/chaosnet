"""Topology spec v1: the services of the lab and the links between them (#72).

Format designed by Tomáš (2026-10-19). One file describes the lab; `compose.yaml`,
`toxiproxy.json` and the UI are derived from it (Sprint 4 decision 2). Anything that can
be derived is not in the file: every link gets its own Toxiproxy proxy, named
``<from>-<to>``.

Pydantic checks the shape (fields, types, ranges). ``check`` checks the rules between
the parts, which Pydantic cannot see.
"""

import re

from pydantic import BaseModel, ConfigDict, Field, model_validator

LATEST_VERSION = 1


class Service(BaseModel):
    name: str
    port: int | None = Field(default=None, ge=1, le=65535)  # published on the Mac: the entry


class Link(BaseModel):
    """A call from one service to another; the timeout and retries belong to the call."""

    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")  # `from` is a Python keyword
    to: str
    timeout_s: float = Field(default=1.0, gt=0)  # per attempt
    max_retries: int = Field(default=0, ge=0)  # no retries unless asked: retries amplify load
    backoff_s: float = Field(default=0.0, ge=0)  # wait before a retry, doubled each time (#119)
    breaker: bool = False  # a circuit breaker on this link, at the caller (ADR-008)

    @property
    def name(self) -> str:
        return f"{self.from_}-{self.to}"


class Topology(BaseModel):
    version: int
    services: list[Service]
    links: list[Link]

    @model_validator(mode="after")
    def rules(self) -> Topology:
        check(self)
        return self


def check(topology: Topology) -> None:
    """Raise ValueError when a rule from the plan in #72 is broken, naming what is wrong."""
    if topology.version > LATEST_VERSION or topology.version < 1:
        raise ValueError(f"unknown version {topology.version}")
    services: set[str] = set()
    links: set[str] = set()
    entry: str | None = None  # the first service with a port
    for s in topology.services:
        if s.name in services:
            raise ValueError(f"services contain duplicate {s.name}")
        if re.fullmatch(r"[a-z0-9]+", s.name) is None:
            raise ValueError(f"wrong syntax for service with name '{s.name}'")
        services.add(s.name)
        if s.port is not None:
            if entry is not None:
                raise ValueError(f"two services have a port: {entry} and {s.name}")
            entry = s.name
    if entry is None:
        raise ValueError("no service has a port")
    calls: dict[str, list[str]] = {name: [] for name in services}  # who calls whom
    for link in topology.links:
        for end in (link.from_, link.to):
            if end not in services:
                raise ValueError(f"unknown service {end} in the link {link.from_}-{link.to}")
        if link.from_ + "-" + link.to in links:
            raise ValueError(f"link {link.from_}-{link.to} cannot be there twice")
        if link.from_ == link.to:
            raise ValueError(f"link {link.from_}-{link.to} links {link.from_} to itself")
        links.add(link.from_ + "-" + link.to)
        calls[link.from_].append(link.to)

    def walk(service: str, path: list[str]) -> None:
        # A service already on the current path means we came back to it: a cycle.
        # Reaching it again on a different path is fine (s1 -> s2 -> s4, s1 -> s3 -> s4).
        if service in path:
            raise ValueError(f"cycle: {' -> '.join([*path, service])}")
        for callee in calls[service]:
            walk(callee, [*path, service])

    # ponytail: walks every path, exponential on many diamonds; fine for a lab of a few
    # services, remember finished services if topologies ever grow large.
    for name in services:
        walk(name, [])
