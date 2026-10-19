"""Tests for the topology rules planned by Tomáš in #72.

A rejected topology must say what is wrong. Each test checks that the error message
contains the offending name(s) and one keyword:

    rule 1  unknown version        "version"
    rule 2  duplicate service      "duplicate"
    rule 3  link to a non-service  "unknown"
    rule 4  link to itself         "itself"
            the same link twice    "twice"
    rule 5  services call in a     "cycle"
            circle
    rule 6  not exactly one port   "port"
    rule 7  bad service name       "name"
"""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from chaosnet.topology import Topology

LAB = Path(__file__).parents[2] / "lab" / "topology.json"


def topology(
    *links: tuple[str, str], port: str | None = "a", names: str = "abcd"
) -> dict[str, Any]:
    """A small topology: services named by the letters of ``names``, ``port`` on one of them."""
    return {
        "version": 1,
        "services": [{"name": n, **({"port": 8080} if n == port else {})} for n in names],
        "links": [{"from": f, "to": t} for f, t in links],
    }


def assert_rejected(data: dict[str, Any], *words: str) -> None:
    with pytest.raises(ValidationError) as e:
        Topology.model_validate(data)
    for word in words:
        assert word in str(e.value), f"{word!r} missing from: {e.value}"


# --- valid topologies -------------------------------------------------------------------


def test_the_lab_topology_is_valid() -> None:
    lab = Topology.model_validate(json.loads(LAB.read_text()))
    assert [s.name for s in lab.services] == ["gateway", "orders", "inventory"]
    assert [link.name for link in lab.links] == ["gateway-orders", "orders-inventory"]
    assert (lab.links[1].timeout_s, lab.links[1].max_retries) == (0.5, 2)


def test_defaults_for_a_link() -> None:
    link = Topology.model_validate(topology(("a", "b"))).links[0]
    assert (link.timeout_s, link.max_retries) == (1.0, 0)


def test_a_service_called_by_two_others_is_not_a_cycle() -> None:
    # a -> b -> d and a -> c -> d: d is reached twice, but nothing calls back.
    Topology.model_validate(topology(("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")))


def test_a_longer_chain_is_valid() -> None:
    Topology.model_validate(topology(("a", "b"), ("b", "c"), ("c", "d")))


# --- rule 1: version --------------------------------------------------------------------


@pytest.mark.parametrize("version", [0, 2, 7])
def test_unknown_version(version: int) -> None:
    assert_rejected({**topology(("a", "b")), "version": version}, "version", str(version))


# --- rule 2: unique names ---------------------------------------------------------------


def test_duplicate_service() -> None:
    assert_rejected(topology(("a", "b"), names="abb"), "duplicate", "b")


# --- rule 3: links between existing services --------------------------------------------


def test_link_to_unknown_service() -> None:
    assert_rejected(topology(("a", "x")), "unknown", "x")


def test_link_from_unknown_service() -> None:
    assert_rejected(topology(("x", "a")), "unknown", "x")


# --- rule 4: no link to itself, no link twice -------------------------------------------


def test_link_to_itself() -> None:
    assert_rejected(topology(("a", "a")), "itself", "a")


def test_same_link_twice() -> None:
    assert_rejected(topology(("a", "b"), ("a", "b")), "twice", "a-b")


# --- rule 5: no cycles ------------------------------------------------------------------


def test_two_services_calling_each_other() -> None:
    assert_rejected(topology(("a", "b"), ("b", "a")), "cycle")


def test_longer_cycle() -> None:
    assert_rejected(topology(("a", "b"), ("b", "c"), ("c", "d"), ("d", "b")), "cycle")


# --- rule 6: exactly one entry ----------------------------------------------------------


def test_no_service_has_a_port() -> None:
    assert_rejected(topology(("a", "b"), port=None), "port")


def test_two_services_have_a_port() -> None:
    data = topology(("a", "b"))
    data["services"][1]["port"] = 8081
    assert_rejected(data, "port", "a", "b")


# --- rule 7: names ----------------------------------------------------------------------


@pytest.mark.parametrize("name", ["Orders", "order-svc", "order svc", ""])
def test_bad_service_name(name: str) -> None:
    data = topology(("a", "b"))
    data["services"].append({"name": name})
    assert_rejected(data, "name", repr(name))


# --- rule 8: values (Pydantic, already works) -------------------------------------------


@pytest.mark.parametrize(("field", "value"), [("timeout_s", 0), ("max_retries", -1)])
def test_bad_link_values(field: str, value: float) -> None:
    data = topology(("a", "b"))
    data["links"][0][field] = value
    assert_rejected(data, field)


def test_port_out_of_range() -> None:
    data = topology(("a", "b"))
    data["services"][0]["port"] = 70000
    assert_rejected(data, "port")
