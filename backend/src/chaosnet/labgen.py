"""Generates the lab (compose.yaml, toxiproxy.json) from topology.json (#73).

Plan agreed 2026-10-28 (decisions by Tomáš): every service runs the same generic code
and calls the services it links to; every link goes through its own Toxiproxy proxy.
`docker compose up` stays manual: the controller never gets the Docker socket (ADR-002).
"""

from typing import Any

from chaosnet.topology import Link, Topology

FIRST_PROXY_PORT = 8665  # inside the lab network only, never published
SERVICE_PORT = 8000  # every service listens here in its container


def proxy_port(topology: Topology, link: Link) -> int:
    return FIRST_PROXY_PORT + topology.links.index(link)


def toxiproxy_config(topology: Topology) -> list[dict[str, Any]]:
    """One proxy per link, each on its own port: the content of toxiproxy.json."""
    res: list[dict[str, Any]] = []
    for link in topology.links:
        name = link.name
        listen = f"0.0.0.0:{proxy_port(topology, link)}"
        upstream = f"{link.to}:{SERVICE_PORT}"
        enabled = True
        res.append({"name": name, "listen": listen, "upstream": upstream, "enabled": enabled})
    return res
