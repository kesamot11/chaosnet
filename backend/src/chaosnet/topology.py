"""Topology spec v1: the services of the lab and the links between them (#72).

Format designed by Tomáš (2026-10-19). One file describes the lab; `compose.yaml`,
`toxiproxy.json` and the UI are derived from it (Sprint 4 decision 2). Anything that can
be derived is not in the file: every link gets its own Toxiproxy proxy, named
``<from>-<to>``.

Pydantic checks the shape (fields, types, ranges). ``check`` checks the rules between
the parts, which Pydantic cannot see.
"""

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    """Tomáš: raise ValueError when a rule from the plan in #72 is broken.

    See tests/test_topology.py for the rules and the words each message must contain.
    """
    raise NotImplementedError
