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


STREAM_TO_DIRECTION: dict[str, Literal["request", "response"]] = {
    "upstream": "request",
    "downstream": "response",
}


class FaultError(Exception):
    """Toxiproxy refused the operation (unknown link, fault already exists, ...)."""


class FaultDriver:
    """Talks to one Toxiproxy instance. See tests/test_faults.py for the expected behaviour.

    A link holds at most one fault of each kind per direction (the toxic name is
    ``chaosnet-{kind}-{stream}``); adding the same one again raises ``FaultError``.
    Stacking 300 ms on top of 300 ms is not a use case; remove and re-add instead.
    """

    def __init__(self, client: httpx.AsyncClient, api_url: str) -> None:
        self.client = client
        self.api_url = api_url

    async def add_latency(self, link: str, ms: int, direction: Direction) -> list[Fault]:
        if ms <= 0:
            raise ValueError(f"Latency must be > 0 ms, got {ms}")
        return await self._add_toxic(link, "latency", direction, {"latency": ms, "jitter": 0})

    async def add_bandwidth(self, link: str, kbps: int, direction: Direction) -> list[Fault]:
        if kbps <= 0:
            raise ValueError(f"Bandwidth must be > 0 kbps, got {kbps}")
        return await self._add_toxic(link, "bandwidth", direction, {"rate": kbps})

    async def add_reset_peer(self, link: str, direction: Direction = "response") -> list[Fault]:
        return await self._add_toxic(link, "reset_peer", direction, {"timeout": 0})

    async def remove(self, fault: Fault) -> None:
        res = await self.client.delete(f"{self.api_url}/proxies/{fault.link}/toxics/{fault.name}")
        if res.is_error and res.status_code != 404:
            raise FaultError(f"{fault.link}: HTTP {res.status_code} {res.text}")

    async def remove_all(self) -> None:
        res = await self.client.post(f"{self.api_url}/reset")
        res.raise_for_status()

    async def links(self) -> set[str]:
        """Names of the proxies Toxiproxy has, one per link."""
        res = await self.client.get(f"{self.api_url}/proxies")
        if res.is_error:
            raise FaultError(f"listing links failed: HTTP {res.status_code} {res.text}")
        return set(res.json())

    async def list_faults(self) -> list[Fault]:
        res = await self.client.get(f"{self.api_url}/proxies")
        if res.is_error:
            raise FaultError(f"listing faults failed: HTTP {res.status_code} {res.text}")
        data = res.json()
        result: list[Fault] = []
        for link, proxy in data.items():
            for toxic in proxy["toxics"]:
                if not toxic["name"].startswith("chaosnet-"):
                    continue
                result.append(
                    Fault(
                        link,
                        toxic["name"],
                        toxic["type"],
                        STREAM_TO_DIRECTION[toxic["stream"]],
                        toxic["attributes"],
                    )
                )
        return result

    def _get_streams(self, direction: Direction) -> list[str]:
        """Translate our direction into Toxiproxy streams (request: client -> server = upstream)."""
        if direction == "request":
            return ["upstream"]
        if direction == "response":
            return ["downstream"]
        if direction == "both":
            return ["upstream", "downstream"]
        raise ValueError(f"direction must be request, response or both, got {direction!r}")

    async def _add_toxic(
        self, link: str, kind: str, direction: Direction, attributes: dict[str, int]
    ) -> list[Fault]:
        streams = self._get_streams(direction)

        faults: list[Fault] = []
        try:
            for stream in streams:
                name = f"chaosnet-{kind}-{stream}"
                toxic = {
                    "name": name,
                    "type": kind,
                    "stream": stream,
                    "toxicity": 1,
                    "attributes": attributes,
                }
                res = await self.client.post(f"{self.api_url}/proxies/{link}/toxics", json=toxic)
                if res.is_error:
                    raise FaultError(f"{link}: HTTP {res.status_code} {res.text}")
                faults.append(Fault(link, name, kind, STREAM_TO_DIRECTION[stream], attributes))
            return faults
        except Exception:
            for created in faults:
                try:
                    await self.remove(created)
                except Exception:
                    pass
            raise
