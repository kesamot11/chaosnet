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
    - At most ``max_retries + 1`` attempts in total, no sleeping between them (backoff: M6).
    - Every attempt uses ``timeout_s`` as its own timeout (not a total budget).
    - Any HTTP response (200, 404, 500, ...) is returned as-is, without retrying.
      Deciding what a status code means is the caller's job.

    Transport failures. The key question: was the request already sent?
    - Not sent (``ConnectError``, ``ConnectTimeout``): always retried.
    - Maybe processed (``ReadError``, ``RemoteProtocolError``, other timeouts): retried only
      for GET. Repeating a non-idempotent request (e.g. POST "pay") could apply it twice.
    - When no attempt is left: timeouts raise ``DownstreamError(504, hop)``, everything
      else ``DownstreamError(503, hop)``.
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
        except httpx.ReadError, httpx.RemoteProtocolError:
            code = 503
            if method != "GET":
                break
        except httpx.ConnectTimeout:
            code = 504
        except httpx.TimeoutException:
            code = 504
            if method != "GET":
                break

    raise DownstreamError(code, hop)
