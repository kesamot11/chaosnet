"""Generates the lab (compose.yaml, toxiproxy.json) from topology.json (#73).

Plan agreed 2026-10-28 (decisions by Tomáš): every service runs the same generic code
and calls the services it links to; every link goes through its own Toxiproxy proxy.
`docker compose up` stays manual: the controller never gets the Docker socket (ADR-002).
"""

import argparse
import json
from pathlib import Path
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
                "backoff_s": link.backoff_s,
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


# What every lab service shares: one image, one program, one healthcheck.
SERVICE_BASE: dict[str, Any] = {
    "build": ".",
    "image": "chaosnet-lab:dev",
    "command": ["uvicorn", "chaosnet_lab.service:app", "--host", "0.0.0.0", "--port", "8000"],
    "healthcheck": {
        "test": [
            "CMD",
            "python",
            "-c",
            "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/healthz', timeout=1)",
        ],
        "interval": "2s",
        "timeout": "2s",
        "retries": 10,
        "start_period": "10s",
        "start_interval": "1s",
    },
}

# The control plane of the lab, the same for every topology.
CONTROL = ("toxiproxy", "watchdog", "prometheus")

HEADER = """\
# Generated from topology.json by `uv run chaosnet-lab` (in backend/), see #73.
# Do not edit: change topology.json and generate again. Valid YAML, written as JSON.
"""


def compose_config(topology: Topology) -> dict[str, Any]:
    """The whole compose.yaml: Toxiproxy, the watchdog, and one service per node."""
    taken = [s.name for s in topology.services if s.name in CONTROL]
    if taken:
        raise ValueError(f"service names {taken} are taken by the lab's control plane")
    # Checks that the config was loaded, not just that the API answers: a broken
    # toxiproxy.json loads no proxies at all. No shell in the image, so one proxy only.
    first = topology.links[0].name if topology.links else None
    services: dict[str, Any] = {
        "toxiproxy": {
            "image": "ghcr.io/shopify/toxiproxy:2.12.0",
            "command": ["-host=0.0.0.0", "-config=/config/toxiproxy.json"],
            "volumes": ["./toxiproxy.json:/config/toxiproxy.json:ro"],
            "ports": ["127.0.0.1:${TOXIPROXY_PORT:-8474}:8474"],
            "healthcheck": {
                **SERVICE_BASE["healthcheck"],
                "test": ["CMD", "/toxiproxy-cli", *(["inspect", first] if first else ["list"])],
            },
        },
        # Cleanup layer 3 (ADR-001): removes all faults when the controller stops
        # sending heartbeats for LEASE_TIMEOUT_S.
        "watchdog": {
            **SERVICE_BASE,
            "command": [
                "uvicorn",
                "chaosnet_lab.watchdog:app",
                "--host",
                "0.0.0.0",
                "--port",
                "8000",
            ],
            "ports": ["127.0.0.1:${WATCHDOG_PORT:-8475}:8000"],
            "environment": {
                "TOXIPROXY_URL": "http://toxiproxy:8474",
                "LEASE_TIMEOUT_S": "${LEASE_TIMEOUT_S:-5}",
                "CHECK_INTERVAL_S": "${CHECK_INTERVAL_S:-0.5}",
            },
            "depends_on": {"toxiproxy": {"condition": "service_healthy"}},
        },
        # Counts requests per service and attempts per hop (#116); the only way to read
        # the services' /metrics, whose ports are never published.
        "prometheus": {
            "image": "prom/prometheus:v3.15.1",
            "command": ["--config.file=/etc/prometheus/prometheus.yml"],
            "volumes": ["./prometheus.yml:/etc/prometheus/prometheus.yml:ro"],
            "ports": ["127.0.0.1:${PROMETHEUS_PORT:-9090}:9090"],
            "healthcheck": {
                **SERVICE_BASE["healthcheck"],
                "test": ["CMD", "wget", "-qO-", "http://127.0.0.1:9090/-/ready"],
            },
        },
    }
    for service in topology.services:
        services[service.name] = {**SERVICE_BASE, **service_config(topology, service.name)}
    return {"name": "chaosnet-lab", "services": services}


def prometheus_config(topology: Topology) -> dict[str, Any]:
    """prometheus.yml: scrape every lab service each second, labelled by its name."""
    return {
        "global": {"scrape_interval": "1s"},
        "scrape_configs": [
            {
                "job_name": "lab",
                "static_configs": [
                    {"targets": [f"{s.name}:{SERVICE_PORT}"], "labels": {"service": s.name}}
                    for s in topology.services
                ],
            }
        ],
    }


def write_lab(topology_file: Path, out: Path) -> None:
    """Write compose.yaml and toxiproxy.json for the topology in `topology_file` to `out`."""
    topology = Topology.model_validate_json(topology_file.read_text())
    compose = HEADER + json.dumps(compose_config(topology), indent=2) + "\n"
    (out / "compose.yaml").write_text(compose)
    (out / "toxiproxy.json").write_text(json.dumps(toxiproxy_config(topology), indent=2) + "\n")
    prometheus = HEADER + json.dumps(prometheus_config(topology), indent=2) + "\n"
    (out / "prometheus.yml").write_text(prometheus)


def main() -> None:
    """uv run chaosnet-lab [--topology FILE] [--out DIR]; by default the lab in lab/."""
    lab = Path(__file__).parents[3] / "lab"
    parser = argparse.ArgumentParser(description="Generate the lab from a topology.")
    parser.add_argument("--topology", type=Path, default=lab / "topology.json")
    parser.add_argument("--out", type=Path, default=lab, help="directory to write to")
    args = parser.parse_args()
    write_lab(args.topology, args.out)
    print(f"wrote compose.yaml, toxiproxy.json and prometheus.yml to {args.out}")
