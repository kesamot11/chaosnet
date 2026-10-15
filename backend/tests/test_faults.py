"""Behaviour of the fault driver, against a fake Toxiproxy.

The fake answers exactly like the real Toxiproxy 2.12.0 (status codes and bodies were
recorded from the lab on 2026-10-14): 200 on create, 409 for an existing toxic name,
404 for an unknown proxy or toxic, 204 on delete and reset.
"""

import asyncio
from collections.abc import Awaitable, Callable

import httpx
import pytest
from fakes import API, LINK, FakeToxiproxy

from chaosnet.faults import Fault, FaultDriver, FaultError


def run[T](action: Callable[[FaultDriver], Awaitable[T]], fake: FakeToxiproxy | None = None) -> T:
    fake = fake or FakeToxiproxy()

    async def go() -> T:
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handle)) as client:
            return await action(FaultDriver(client, API))

    return asyncio.run(go())


# --- adding faults -------------------------------------------------------------------


def test_latency_on_requests_delays_the_upstream_stream() -> None:
    fake = FakeToxiproxy()
    faults = run(lambda d: d.add_latency(LINK, 300, "request"), fake)
    assert [f.direction for f in faults] == ["request"]
    [toxic] = fake.toxics[LINK]
    assert (toxic["type"], toxic["stream"]) == ("latency", "upstream")
    assert toxic["attributes"]["latency"] == 300


def test_latency_on_responses_delays_the_downstream_stream() -> None:
    fake = FakeToxiproxy()
    run(lambda d: d.add_latency(LINK, 300, "response"), fake)
    assert [t["stream"] for t in fake.toxics[LINK]] == ["downstream"]


def test_latency_in_both_directions_creates_two_faults() -> None:
    # 300 ms each way means +600 ms round trip.
    fake = FakeToxiproxy()
    faults = run(lambda d: d.add_latency(LINK, 300, "both"), fake)
    assert sorted(f.direction for f in faults) == ["request", "response"]
    assert sorted(t["stream"] for t in fake.toxics[LINK]) == ["downstream", "upstream"]
    assert all(t["attributes"]["latency"] == 300 for t in fake.toxics[LINK])


def test_bandwidth_limits_the_rate_in_kbps() -> None:
    fake = FakeToxiproxy()
    [fault] = run(lambda d: d.add_bandwidth(LINK, 64, "response"), fake)
    [toxic] = fake.toxics[LINK]
    assert (toxic["type"], toxic["stream"], toxic["attributes"]["rate"]) == (
        "bandwidth",
        "downstream",
        64,
    )
    assert fault.kind == "bandwidth"


def test_reset_peer_cuts_connections_immediately() -> None:
    fake = FakeToxiproxy()
    [fault] = run(lambda d: d.add_reset_peer(LINK), fake)
    [toxic] = fake.toxics[LINK]
    assert toxic["type"] == "reset_peer"
    assert toxic["attributes"]["timeout"] == 0
    assert fault.link == LINK


def test_faults_are_marked_as_chaosnet_and_have_unique_names() -> None:
    fake = FakeToxiproxy()

    async def add_several(d: FaultDriver) -> list[Fault]:
        return [
            *await d.add_latency(LINK, 100, "both"),
            *await d.add_bandwidth(LINK, 64, "request"),
        ]

    faults = run(add_several, fake)
    names = [f.name for f in faults]
    assert all(n.startswith("chaosnet-") for n in names)
    assert len(set(names)) == len(names) == 3


def test_returned_fault_matches_what_toxiproxy_stored() -> None:
    fake = FakeToxiproxy()
    [fault] = run(lambda d: d.add_latency(LINK, 250, "request"), fake)
    [toxic] = fake.toxics[LINK]
    assert fault == Fault(LINK, toxic["name"], "latency", "request", toxic["attributes"])


# --- errors --------------------------------------------------------------------------


def test_adding_the_same_fault_twice_fails_with_the_link_name() -> None:
    async def twice(d: FaultDriver) -> None:
        await d.add_latency(LINK, 300, "request")
        await d.add_latency(LINK, 300, "request")

    with pytest.raises(FaultError, match=LINK):
        run(twice)


def test_partial_both_failure_removes_already_created_toxic() -> None:
    fake = FakeToxiproxy()
    fake.toxics[LINK].append(
        {
            "name": "chaosnet-latency-downstream",
            "type": "latency",
            "stream": "downstream",
            "toxicity": 1,
            "attributes": {"latency": 300, "jitter": 0},
        }
    )

    with pytest.raises(FaultError, match=LINK):
        run(lambda d: d.add_latency(LINK, 300, "both"), fake)

    assert [t["name"] for t in fake.toxics[LINK]] == ["chaosnet-latency-downstream"]


def test_unknown_link_fails_with_its_name() -> None:
    with pytest.raises(FaultError, match="no-such-link"):
        run(lambda d: d.add_latency("no-such-link", 300, "request"))


async def zero_ms(d: FaultDriver) -> object:
    return await d.add_latency(LINK, 0, "request")


async def negative_ms(d: FaultDriver) -> object:
    return await d.add_latency(LINK, -5, "request")


async def bad_direction(d: FaultDriver) -> object:
    # Direction comes from CLI input at runtime, so the type checker cannot stop this.
    return await d.add_latency(LINK, 300, "sideways")  # pyright: ignore[reportArgumentType]


async def zero_kbps(d: FaultDriver) -> object:
    return await d.add_bandwidth(LINK, 0, "request")


@pytest.mark.parametrize("action", [zero_ms, negative_ms, bad_direction, zero_kbps])
def test_invalid_input_is_rejected_before_calling_toxiproxy(
    action: Callable[[FaultDriver], Awaitable[object]],
) -> None:
    fake = FakeToxiproxy()
    with pytest.raises(ValueError, match=r"0|-5|sideways"):
        run(action, fake)
    assert fake.requests == []


# --- removing and listing ------------------------------------------------------------


def test_remove_deletes_only_that_fault() -> None:
    fake = FakeToxiproxy()

    async def add_two_remove_one(d: FaultDriver) -> None:
        [keep] = await d.add_latency(LINK, 100, "request")
        [drop] = await d.add_bandwidth(LINK, 64, "response")
        await d.remove(drop)
        assert keep.name in [t["name"] for t in fake.toxics[LINK]]

    run(add_two_remove_one, fake)
    assert [t["type"] for t in fake.toxics[LINK]] == ["latency"]


def test_remove_is_idempotent() -> None:
    # Cleanup can run twice (CLI after the watchdog already reset): it must not fail.
    async def remove_twice(d: FaultDriver) -> None:
        [fault] = await d.add_latency(LINK, 100, "request")
        await d.remove(fault)
        await d.remove(fault)

    run(remove_twice)


def test_remove_all_clears_every_link() -> None:
    fake = FakeToxiproxy()

    async def add_and_reset(d: FaultDriver) -> None:
        await d.add_latency(LINK, 100, "both")
        await d.add_reset_peer("gateway-orders")
        await d.remove_all()

    run(add_and_reset, fake)
    assert fake.toxics == {"gateway-orders": [], LINK: []}


def test_list_faults_returns_only_chaosnet_faults() -> None:
    fake = FakeToxiproxy()
    fake.toxics[LINK].append(
        {
            "name": "someone-else",
            "type": "latency",
            "stream": "upstream",
            "toxicity": 1,
            "attributes": {"latency": 5},
        }
    )

    async def add_and_list(d: FaultDriver) -> tuple[list[Fault], list[Fault]]:
        added = await d.add_latency(LINK, 300, "both")
        return added, await d.list_faults()

    added, listed = run(add_and_list, fake)
    assert sorted(listed, key=lambda f: f.name) == sorted(added, key=lambda f: f.name)


def test_list_faults_is_empty_on_a_clean_lab() -> None:
    assert run(lambda d: d.list_faults()) == []


# --- Toxiproxy itself failing (found in review of #39) --------------------------------


def broken(response: httpx.Response) -> FakeToxiproxy:
    fake = FakeToxiproxy()
    fake.handle = lambda request: response  # type: ignore[method-assign]
    return fake


def test_list_faults_fails_clearly_when_toxiproxy_errors() -> None:
    fake = broken(httpx.Response(500, json={"error": "boom", "status": 500}))
    with pytest.raises(FaultError, match="HTTP 500"):
        run(lambda d: d.list_faults(), fake)


def test_add_fails_clearly_when_error_body_is_not_json() -> None:
    fake = broken(httpx.Response(502, text="<html>Bad Gateway</html>"))
    with pytest.raises(FaultError, match=f"{LINK}: HTTP 502"):
        run(lambda d: d.add_latency(LINK, 100, "request"), fake)


def test_remove_fails_clearly_when_error_body_is_not_json() -> None:
    fake = broken(httpx.Response(500, text="oops"))
    fault = Fault(LINK, "chaosnet-latency-upstream", "latency", "request", {})
    with pytest.raises(FaultError, match=f"{LINK}: HTTP 500"):
        run(lambda d: d.remove(fault), fake)
