import asyncio
from collections.abc import Callable

import httpx
import pytest

from chaosnet_lab.client import DownstreamError, call_downstream

URL = "http://inventory:8000/items/42"
HOP = "orders->inventory"

# A fake downstream: each element is either a status code to answer with,
# or an exception to raise instead of answering.
Script = list[int | Exception]


class FakeDownstream:
    def __init__(self, script: Script) -> None:
        self.script = script
        self.requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        step = self.script[min(len(self.requests), len(self.script)) - 1]
        if isinstance(step, Exception):
            raise step
        return httpx.Response(step, json={"item_id": "42"})


def run(
    script: Script, *, max_retries: int = 2, timeout_s: float = 0.5, method: str = "GET"
) -> tuple[Callable[[], httpx.Response], FakeDownstream]:
    fake = FakeDownstream(script)

    def call() -> httpx.Response:
        async def go() -> httpx.Response:
            async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handle)) as client:
                return await call_downstream(
                    client, method, URL, hop=HOP, timeout_s=timeout_s, max_retries=max_retries
                )

        return asyncio.run(go())

    return call, fake


def refused() -> httpx.ConnectError:
    return httpx.ConnectError("[Errno 111] Connection refused")


def unresolvable() -> httpx.ConnectError:
    return httpx.ConnectError("[Errno -2] Name or service not known")


def timed_out() -> httpx.ReadTimeout:
    return httpx.ReadTimeout("timed out")


def test_success_on_first_attempt() -> None:
    call, fake = run([200])
    assert call().status_code == 200
    assert len(fake.requests) == 1


def test_http_error_responses_are_returned_without_retry() -> None:
    for status in (404, 500, 503):
        call, fake = run([status])
        assert call().status_code == status
        assert len(fake.requests) == 1, f"{status} must not be retried"


@pytest.mark.parametrize("error", [refused, unresolvable])
def test_unreachable_downstream_raises_503_after_all_attempts(
    error: Callable[[], Exception],
) -> None:
    call, fake = run([error()], max_retries=2)
    with pytest.raises(DownstreamError) as exc:
        call()
    assert exc.value.status_code == 503
    assert exc.value.failed_hop == HOP
    assert len(fake.requests) == 3


def test_hanging_downstream_raises_504_after_all_attempts() -> None:
    call, fake = run([timed_out()], max_retries=2)
    with pytest.raises(DownstreamError) as exc:
        call()
    assert exc.value.status_code == 504
    assert exc.value.failed_hop == HOP
    assert len(fake.requests) == 3


def test_connect_timeout_counts_as_timeout() -> None:
    call, _ = run([httpx.ConnectTimeout("timed out")], max_retries=0)
    with pytest.raises(DownstreamError) as exc:
        call()
    assert exc.value.status_code == 504


def test_recovers_when_a_retry_succeeds() -> None:
    call, fake = run([refused(), timed_out(), 200], max_retries=2)
    assert call().status_code == 200
    assert len(fake.requests) == 3


def test_last_failure_decides_the_status() -> None:
    call, _ = run([timed_out(), refused()], max_retries=1)
    with pytest.raises(DownstreamError) as exc:
        call()
    assert exc.value.status_code == 503


def test_zero_retries_means_exactly_one_attempt() -> None:
    call, fake = run([refused()], max_retries=0)
    with pytest.raises(DownstreamError):
        call()
    assert len(fake.requests) == 1


def test_timeout_applies_to_each_attempt() -> None:
    call, fake = run([timed_out(), 200], max_retries=1, timeout_s=0.25)
    call()
    for request in fake.requests:
        assert request.extensions["timeout"]["read"] == 0.25
        assert request.extensions["timeout"]["connect"] == 0.25


def test_negative_max_retries_is_rejected_before_any_request() -> None:
    call, fake = run([200], max_retries=-1)
    with pytest.raises(ValueError, match="max_retries"):
        call()
    assert fake.requests == []


# --- Sprint 2: a proxy between services turns "downstream is down" into an error that
# happens AFTER the request was sent (the connection is cut while reading the answer).


def cut_after_send() -> httpx.ReadError:
    return httpx.ReadError("connection closed by peer")


def disconnected() -> httpx.RemoteProtocolError:
    return httpx.RemoteProtocolError("Server disconnected without sending a response.")


@pytest.mark.parametrize("error", [cut_after_send, disconnected])
def test_get_cut_after_send_is_retried_then_503(error: Callable[[], Exception]) -> None:
    call, fake = run([error()], max_retries=2, method="GET")
    with pytest.raises(DownstreamError) as exc:
        call()
    assert exc.value.status_code == 503
    assert len(fake.requests) == 3


@pytest.mark.parametrize("error", [cut_after_send, disconnected])
def test_post_cut_after_send_is_not_retried(error: Callable[[], Exception]) -> None:
    # The downstream may already have processed the POST; repeating it could double it.
    call, fake = run([error(), 200], max_retries=2, method="POST")
    with pytest.raises(DownstreamError) as exc:
        call()
    assert exc.value.status_code == 503
    assert len(fake.requests) == 1


def test_post_connect_error_is_still_retried() -> None:
    # A connection that never opened means the request was never sent: always safe to retry.
    call, fake = run([refused(), 200], max_retries=2, method="POST")
    assert call().status_code == 200
    assert len(fake.requests) == 2


def test_get_recovers_after_a_cut() -> None:
    call, fake = run([cut_after_send(), 200], max_retries=2, method="GET")
    assert call().status_code == 200
    assert len(fake.requests) == 2
