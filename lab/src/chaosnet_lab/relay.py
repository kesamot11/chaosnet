"""Glue shared by services that call a downstream service (gateway, orders)."""

import os
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi.responses import JSONResponse, Response

from chaosnet_lab.client import DownstreamError, call_downstream


@dataclass(frozen=True)
class Hop:
    name: str  # e.g. "orders->inventory"
    url: str
    timeout_s: float
    max_retries: int

    @classmethod
    def from_env(cls, name: str) -> Hop:
        """Read the hop config from the environment and fail fast on bad values."""
        url = os.environ.get("DOWNSTREAM_URL", "")
        parsed = httpx.URL(url)
        if parsed.scheme not in ("http", "https") or not parsed.host:
            raise ValueError(f"DOWNSTREAM_URL must be http(s)://host[:port], got {url!r}")
        timeout_s = float(os.environ.get("TIMEOUT_S", "0.5"))
        max_retries = int(os.environ.get("MAX_RETRIES", "2"))
        if timeout_s <= 0:
            raise ValueError(f"TIMEOUT_S must be > 0, got {timeout_s}")
        if max_retries < 0:
            raise ValueError(f"MAX_RETRIES must be >= 0, got {max_retries}")
        return cls(name, url, timeout_s, max_retries)


async def relay(
    client: httpx.AsyncClient, hop: Hop, method: str, path: str, *, service: str, json: Any = None
) -> Response:
    """Call the downstream hop and turn the outcome into this service's response.

    - transport failure -> 503/504 naming the failed hop
    - downstream HTTP error (404, 503, ...) -> passed through unchanged
    - success -> downstream body with this service prepended to "path"
    """
    try:
        res = await call_downstream(
            client,
            method,
            hop.url + path,
            hop=hop.name,
            timeout_s=hop.timeout_s,
            max_retries=hop.max_retries,
            json=json,
        )
    except DownstreamError as e:
        reason = "unavailable" if e.status_code == 503 else "timeout"
        return JSONResponse({"error": reason, "failed_hop": e.failed_hop}, e.status_code)

    if res.is_error:
        return Response(res.content, res.status_code, media_type=res.headers.get("content-type"))

    body = res.json()
    body["path"] = [service, *body["path"]]
    return JSONResponse(body)
