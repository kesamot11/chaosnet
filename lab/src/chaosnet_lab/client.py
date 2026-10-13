"""Calls between services: per-attempt timeout, retries, and error classification."""

from typing import Any

import httpx


class DownstreamError(Exception):
    """A downstream service could not be reached after all attempts."""

    def __init__(self, status_code: int, failed_hop: str) -> None:
        super().__init__(f"{failed_hop} failed with {status_code}")
        self.status_code = status_code  # 503 = unavailable, 504 = timed out
        self.failed_hop = failed_hop  # e.g. "orders->inventory"


async def call_downstream(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    hop: str,
    timeout_s: float,
    max_retries: int,
    json: Any = None,
) -> httpx.Response:
    """Call another service, retrying transport failures.

    Rules (tests/test_client.py checks every one):
    - At most ``max_retries + 1`` attempts in total.
    - Every attempt uses ``timeout_s`` as its own timeout (not a total budget).
    - Any HTTP response (200, 404, 500, ...) is returned as-is, without retrying.
      Deciding what a status code means is the caller's job.
    - ``httpx.ConnectError`` (connection refused, name not resolvable) is retried.
      If the last attempt failed this way, raise ``DownstreamError(503, hop)``.
    - ``httpx.TimeoutException`` (no answer in time) is retried.
      If the last attempt failed this way, raise ``DownstreamError(504, hop)``.
    - No sleeping between attempts (backoff comes in M6).

    Useful API:
    - ``await client.request(method, url, json=json, timeout=timeout_s)``
    - ``try: ... except httpx.ConnectError: ... except httpx.TimeoutException: ...``
    """
    if max_retries < 0:
        raise ValueError(f"max_retries must be >= 0, not {max_retries}")
    code = 503
    for _ in range(max_retries + 1):
        try:
            res = await client.request(method, url, json=json, timeout=timeout_s)
            return res
        except httpx.ConnectError:
            code = 503
        except httpx.TimeoutException:
            code = 504

    raise DownstreamError(code, hop)
