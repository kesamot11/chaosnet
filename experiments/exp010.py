"""EXP-010 (#177): inventory paused for a 20 s load at 20 req/s, with orders -> inventory
in three configurations: A no fallback, B fallback, C fallback and breaker.

For each one the lab is generated from a variant of lab/topology.json and recreated
(fresh services: breaker closed), then it prints the outcomes, the median latency, the
attempts on orders -> inventory and the fallbacks counted by orders. At the end the
default lab is generated and started again.

    python3 experiments/exp010.py backend lab
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

BACKEND, LAB = sys.argv[1], Path(sys.argv[2])
CONFIGS = {"A": {}, "B": {"fallback": True}, "C": {"fallback": True, "breaker": True}}


def counters() -> dict[str, float]:
    """orders' own counters for orders -> inventory, read in the container itself.

    The services are recreated for every configuration, so they start at zero; read
    directly, without Prometheus, whose last samples of the old container could still
    be returned (the first run of this script subtracted them and was discarded).
    """
    code = "import urllib.request as u; print(u.urlopen('http://127.0.0.1:8000/metrics').read().decode())"
    text = run("docker", "compose", "exec", "-T", "orders", "python", "-c", code, cwd=LAB)
    out: dict[str, float] = {}
    for line in text.splitlines():
        if 'hop="orders->inventory"' not in line or line.startswith("#"):
            continue
        name, value = line.rsplit(" ", 1)
        if name.startswith("lab_attempts_total"):
            out[name.split('outcome="')[1].split('"')[0]] = float(value)
        elif name.startswith("lab_fallbacks_total"):
            out["fallbacks"] = float(value)
    return out


def run(*args: str, cwd: str | Path) -> str:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout


def lab(topology: Path) -> None:
    run(
        "uv",
        "run",
        "chaosnet-lab",
        "--topology",
        str(topology),
        "--out",
        str(LAB.resolve()),
        cwd=BACKEND,
    )
    run(
        "docker",
        "compose",
        "up",
        "-d",
        "--build",
        "--force-recreate",
        "--wait",
        cwd=LAB,
    )


default = json.loads((LAB / "topology.json").read_text())
try:
    for name, extra in CONFIGS.items():
        variant = json.loads(json.dumps(default))
        variant["links"][1].update(extra)  # orders -> inventory
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(variant, f)
        lab(Path(f.name))
        assert counters() == {}, "fresh services count nothing yet"
        run("docker", "compose", "pause", "inventory", cwd=LAB)
        try:
            out = run(
                "uv",
                "run",
                "python",
                "-m",
                "chaosnet.loadgen",
                "http://127.0.0.1:8080/orders",
                "--rate",
                "20",
                "--duration",
                "20",
                cwd=BACKEND,
            )
        finally:
            run("docker", "compose", "unpause", "inventory", cwd=LAB)
        time.sleep(2)  # let calls on their way finish
        report = json.loads(out)
        delta = counters()
        print(f"== {name} {extra}")
        print("  outcomes", report["outcomes"])
        print("  latency all", report["latency_ms"]["all"])
        print("  orders->inventory", delta)
        print("  per second p50:", [s["p50"] for s in report["per_second"]])
finally:
    lab((LAB / "topology.json").resolve())
