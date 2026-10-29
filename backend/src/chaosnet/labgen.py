"""Generates the lab (compose.yaml, toxiproxy.json) from topology.json (#73).

Plan agreed 2026-10-28 (decisions by Tomáš): every service runs the same generic code
and calls the services it links to; every link goes through its own Toxiproxy proxy.
`docker compose up` stays manual: the controller never gets the Docker socket (ADR-002).
"""

import json
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


def service_config(topology: Topology, service: str) -> dict[str, Any]:
    """The part of one service in compose.yaml that comes from the topology.

    - environment: SERVICE_NAME, and CALLS as JSON (see lab/src/chaosnet_lab/service.py):
      one entry per link from this service, through the link's proxy
    - depends_on: every service it calls, and toxiproxy, all healthy
    - ports: only the entry (the service with a port), on 127.0.0.1, overridable with
      ENTRY_PORT, e.g. "127.0.0.1:${ENTRY_PORT:-8080}:8000"
    """
    outgoing = [link for link in topology.links if link.from_ == service]
    calls: list[dict[str, Any]] = []
    for link in outgoing:
        calls.append(
            {
                "hop": f"{link.from_}->{link.to}",
                "url": f"http://toxiproxy:{proxy_port(topology, link)}",
                "timeout_s": link.timeout_s,
                "max_retries": link.max_retries,
            }
        )
    depends_on: dict[str, Any] = {}
    for link in outgoing:
        depends_on[link.to] = {"condition": "service_healthy"}
    if outgoing:
        depends_on["toxiproxy"] = {"condition": "service_healthy"}
    result: dict[str, Any] = {
        "environment": {"SERVICE_NAME": service, "CALLS": json.dumps(calls)},
        "depends_on": depends_on,
    }
    for s in topology.services:
        if s.name == service and s.port is not None:
            result["ports"] = [f"127.0.0.1:${{ENTRY_PORT:-{s.port}}}:{SERVICE_PORT}"]
    return result
