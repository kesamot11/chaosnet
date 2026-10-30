"""EXP-005 part 2 (#120): a 1 s outage of one link under load, failures counted.

    python3 experiments/exp005.py backend

20 req/s for 6 s through the load generator; the orders-inventory proxy is disabled
from 2.5 s to 3.5 s, so every connection to inventory is refused. Prints the outcomes,
the per-second error rate and the attempts on the link from Prometheus.
"""

import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request

BACKEND = sys.argv[1]
TOXIPROXY = "http://127.0.0.1:8474/proxies/orders-inventory"
PROM = "http://127.0.0.1:9090/api/v1/query?query="


def proxy(enabled: bool) -> None:
    body = json.dumps({"enabled": enabled}).encode()
    req = urllib.request.Request(TOXIPROXY, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    urllib.request.urlopen(req, timeout=5).close()


def attempts() -> dict[str, float]:
    time.sleep(2.5)  # Prometheus scrapes every second
    query = 'lab_attempts_total{hop="orders->inventory"}'
    with urllib.request.urlopen(PROM + urllib.parse.quote(query)) as r:
        result = json.load(r)["data"]["result"]
    return {x["metric"]["outcome"]: float(x["value"][1]) for x in result}


before = attempts()
load = subprocess.Popen(
    ["uv", "run", "python", "-m", "chaosnet.loadgen", "http://127.0.0.1:8080/orders",
     "--rate", "20", "--duration", "6"],
    cwd=BACKEND, stdout=subprocess.PIPE, text=True,
)
time.sleep(2.5 + 0.3)  # the load generator needs ~0.3 s to start
try:
    proxy(False)
    time.sleep(1.0)
finally:
    proxy(True)
report = json.loads(load.communicate()[0])
after = attempts()
print("outcomes", report["outcomes"])
print("error rate per second", [s["error_rate"] for s in report["per_second"]])
print("p95 ms per second", [s["p95"] for s in report["per_second"]])
print("p95 ms all", report["latency_ms"]["all"]["p95"], "| p95 ms ok", report["latency_ms"]["ok"]["p95"])
print("attempts orders->inventory", {k: after.get(k, 0) - before.get(k, 0) for k in after})
