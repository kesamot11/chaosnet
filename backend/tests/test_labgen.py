"""Tests for generating the lab from a topology (#73)."""

import json
from pathlib import Path
from typing import Any

import pytest

from chaosnet.labgen import (
    HEADER,
    compose_config,
    prometheus_config,
    service_config,
    toxiproxy_config,
)
from chaosnet.topology import Topology

LAB = Path(__file__).parents[2] / "lab"


def topology(*links: tuple[str, str]) -> Topology:
    names = sorted({name for link in links for name in link})
    return Topology.model_validate(
        {
            "version": 1,
            "services": [
                {"name": n, **({"port": 8080} if i == 0 else {})} for i, n in enumerate(names)
            ],
            "links": [{"from": f, "to": t} for f, t in links],
        }
    )


def test_one_proxy_per_link_each_on_its_own_port() -> None:
    assert toxiproxy_config(topology(("a", "b"), ("b", "c"))) == [
        {"name": "a-b", "listen": "0.0.0.0:8665", "upstream": "b:8000", "enabled": True},
        {"name": "b-c", "listen": "0.0.0.0:8666", "upstream": "c:8000", "enabled": True},
    ]


def test_a_service_called_by_two_others_gets_two_proxies() -> None:
    proxies = toxiproxy_config(topology(("a", "c"), ("b", "c")))
    assert [p["upstream"] for p in proxies] == ["c:8000", "c:8000"]
    assert len({p["listen"] for p in proxies}) == 2


def test_no_links_no_proxies() -> None:
    lone = Topology.model_validate(
        {"version": 1, "services": [{"name": "a", "port": 8080}], "links": []}
    )
    assert toxiproxy_config(lone) == []


def test_the_default_lab_gives_todays_toxiproxy_json() -> None:
    lab = Topology.model_validate_json((LAB / "topology.json").read_text())
    assert toxiproxy_config(lab) == json.loads((LAB / "toxiproxy.json").read_text())


# --- service_config ---------------------------------------------------------------------


def calls(config: dict[str, Any]) -> list[dict[str, Any]]:
    return json.loads(config["environment"]["CALLS"])


def test_a_service_calls_through_the_proxy_of_its_link() -> None:
    lab = Topology.model_validate_json((LAB / "topology.json").read_text())
    orders = service_config(lab, "orders")
    assert orders["environment"]["SERVICE_NAME"] == "orders"
    assert calls(orders) == [
        {
            "hop": "orders->inventory",
            "url": "http://toxiproxy:8666",
            "timeout_s": 0.5,
            "max_retries": 2,
        }
    ]
    assert orders["depends_on"] == {
        "inventory": {"condition": "service_healthy"},
        "toxiproxy": {"condition": "service_healthy"},
    }
    assert "ports" not in orders  # only the entry is reachable from the Mac


def test_only_the_entry_publishes_its_port_on_localhost() -> None:
    lab = Topology.model_validate_json((LAB / "topology.json").read_text())
    assert service_config(lab, "gateway")["ports"] == ["127.0.0.1:${ENTRY_PORT:-8080}:8000"]


def test_a_leaf_calls_nobody_and_waits_for_nobody() -> None:
    leaf = service_config(topology(("a", "b")), "b")
    assert calls(leaf) == []
    assert leaf["depends_on"] == {}


def test_a_service_calling_two_others_calls_both_with_their_own_settings() -> None:
    t = Topology.model_validate(
        {
            "version": 1,
            "services": [{"name": "a", "port": 8080}, {"name": "b"}, {"name": "c"}],
            "links": [
                {"from": "a", "to": "b", "timeout_s": 2.0, "max_retries": 1},
                {"from": "a", "to": "c", "timeout_s": 0.3, "max_retries": 0},
            ],
        }
    )
    a = service_config(t, "a")
    assert [(c["hop"], c["timeout_s"], c["max_retries"]) for c in calls(a)] == [
        ("a->b", 2.0, 1),
        ("a->c", 0.3, 0),
    ]
    assert set(a["depends_on"]) == {"b", "c", "toxiproxy"}


def test_every_service_calls_exactly_the_ports_toxiproxy_listens_on() -> None:
    # the two halves of the lab must agree on every link's port, or a fault on a link
    # would land on a proxy nobody calls
    t = topology(("a", "b"), ("a", "c"), ("b", "d"), ("c", "d"))
    listened = {p["listen"].split(":")[1] for p in toxiproxy_config(t)}
    called = {
        c["url"].rsplit(":", 1)[1] for s in t.services for c in calls(service_config(t, s.name))
    }
    assert called == listened


# --- compose_config ---------------------------------------------------------------------


def test_compose_has_the_control_plane_and_every_service() -> None:
    lab = Topology.model_validate_json((LAB / "topology.json").read_text())
    services = compose_config(lab)["services"]
    assert list(services) == [
        "toxiproxy",
        "watchdog",
        "prometheus",
        "gateway",
        "orders",
        "inventory",
    ]
    assert services["orders"]["command"][1] == "chaosnet_lab.service:app"
    assert services["toxiproxy"]["healthcheck"]["test"][-1] == "gateway-orders"


def test_a_service_cannot_take_the_name_of_the_control_plane() -> None:
    with pytest.raises(ValueError, match="toxiproxy"):
        compose_config(topology(("a", "toxiproxy")))


def test_the_lab_files_are_generated_from_topology_json() -> None:
    # drift check: someone edited compose.yaml or toxiproxy.json by hand, or changed
    # topology.json without generating again. Fix: `uv run chaosnet-lab`.
    lab = Topology.model_validate_json((LAB / "topology.json").read_text())
    compose = (LAB / "compose.yaml").read_text()
    assert compose.startswith(HEADER)
    assert json.loads(compose.removeprefix(HEADER)) == compose_config(lab)
    assert json.loads((LAB / "toxiproxy.json").read_text()) == toxiproxy_config(lab)
    prometheus = (LAB / "prometheus.yml").read_text()
    assert json.loads(prometheus.removeprefix(HEADER)) == prometheus_config(lab)


def test_prometheus_scrapes_every_service_by_name() -> None:
    lab = Topology.model_validate_json((LAB / "topology.json").read_text())
    targets = prometheus_config(lab)["scrape_configs"][0]["static_configs"]
    assert [(t["targets"], t["labels"]) for t in targets] == [
        (["gateway:8000"], {"service": "gateway"}),
        (["orders:8000"], {"service": "orders"}),
        (["inventory:8000"], {"service": "inventory"}),
    ]
