"""Fault driver: add, remove and list faults on lab links through the Toxiproxy API."""

from dataclasses import dataclass
from typing import Literal

import httpx

Direction = Literal["request", "response", "both"]


@dataclass(frozen=True)
class Fault:
    link: str  # Toxiproxy proxy name, e.g. "orders-inventory"
    name: str  # toxic name inside that proxy; every fault ChaosNet creates starts with "chaosnet-"
    kind: str  # "latency", "bandwidth" or "reset_peer"
    direction: Literal["request", "response"]
    attributes: dict[str, int]


class FaultError(Exception):
    """Toxiproxy refused the operation (unknown link, fault already exists, ...)."""


class FaultDriver:
    """Talks to one Toxiproxy instance. See tests/test_faults.py for the expected behaviour."""

    def __init__(self, client: httpx.AsyncClient, api_url: str) -> None:
        self.client = client
        self.api_url = api_url

    async def add_latency(self, link: str, ms: int, direction: Direction) -> list[Fault]:
        raise NotImplementedError

    async def add_bandwidth(self, link: str, kbps: int, direction: Direction) -> list[Fault]:
        raise NotImplementedError

    async def add_reset_peer(self, link: str) -> list[Fault]:
        raise NotImplementedError

    async def remove(self, fault: Fault) -> None:
        raise NotImplementedError

    async def remove_all(self) -> None:
        raise NotImplementedError

    async def list_faults(self) -> list[Fault]:
        raise NotImplementedError
