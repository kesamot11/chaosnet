"""Tests for generating the lab from a topology (#73)."""

import json
from pathlib import Path

from chaosnet.labgen import toxiproxy_config
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
