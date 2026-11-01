"""EXP-007 (#139): the storm of EXP-004 B under load, with or without a retry budget.

    python3 experiments/exp007.py backend lab

Restarts gateway and orders (so budgets start full), pauses inventory, runs the load
generator at 20 req/s for 20 s, unpauses. Prints attempts per hop and outcome, retries
the budget refused, and the users' latency.
"""

import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request

BACKEND, LAB = sys.argv[1], sys.argv[2]
PROM = "http://127.0.0.1:9090/api/v1/query?query="


def query(q: str) -> dict[tuple[str, str], float]:
    with urllib.request.urlopen(PROM + urllib.parse.quote(q)) as r:
        result = json.load(r)["data"]["result"]
    return {(x["metric"].get("hop", ""), x["metric"].get("outcome", "denied")): float(x["value"][1])
            for x in result}


def counters() -> dict[tuple[str, str], float]:
    time.sleep(2.5)  # Prometheus scrapes every second
    return {**query("lab_attempts_total"), **query("lab_retries_denied_total")}


def compose(*args: str) -> None:
    subprocess.run(["docker", "compose", *args], cwd=LAB, check=True, capture_output=True)


compose("restart", "gateway", "orders")
compose("up", "-d", "--wait")
before = counters()
compose("pause", "inventory")
try:
    load = subprocess.run(
        ["uv", "run", "python", "-m", "chaosnet.loadgen", "http://127.0.0.1:8080/orders",
         "--rate", "20", "--duration", "20"],
        cwd=BACKEND, capture_output=True, text=True, check=True,
    )
finally:
    compose("unpause", "inventory")
time.sleep(3)  # calls on their way finish
after = counters()
report = json.loads(load.stdout)
for key in sorted(after):
    delta = after[key] - before.get(key, 0)
    if delta:
        print(f"{delta:6.0f}  {key[0]} {key[1]}")
lat = report["latency_ms"]["all"]
print("answers", report["outcomes"], "| latency ms p50", lat["p50"], "p95", lat["p95"])
