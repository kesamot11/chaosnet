"""EXP-006 (#137): inventory paused for a 20 s load at 20 req/s, with a breaker on
orders -> inventory. Prints the attempts on that link by outcome, the answers, and per
second the error rate and p95, which show when the breaker opened.

    python3 experiments/exp006.py backend lab
"""

import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BACKEND, LAB = sys.argv[1], sys.argv[2]
PROM = "http://127.0.0.1:9090/api/v1/query?query="


def attempts() -> dict[str, float]:
    time.sleep(2.5)  # Prometheus scrapes every second
    query = 'lab_attempts_total{hop="orders->inventory"}'
    with urllib.request.urlopen(PROM + urllib.parse.quote(query)) as r:
        result = json.load(r)["data"]["result"]
    return {x["metric"]["outcome"]: float(x["value"][1]) for x in result}


def compose(*args: str) -> None:
    subprocess.run(["docker", "compose", *args], cwd=LAB, check=True, capture_output=True)


def closed() -> None:
    """Make sure the breaker is closed: it closes only through a good trial call."""
    for _ in range(20):
        req = urllib.request.Request("http://127.0.0.1:8080/orders", method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10):
                return
        except urllib.error.HTTPError:
            time.sleep(1)
    raise RuntimeError("the breaker did not close")


closed()
before = attempts()
compose("pause", "inventory")
try:
    load = subprocess.run(
        ["uv", "run", "python", "-m", "chaosnet.loadgen", "http://127.0.0.1:8080/orders",
         "--rate", "20", "--duration", "20"],
        cwd=BACKEND, capture_output=True, text=True, check=True,
    )
finally:
    compose("unpause", "inventory")
time.sleep(2)  # let calls on their way finish
report = json.loads(load.stdout)
after = attempts()
print("outcomes", report["outcomes"])
print("attempts orders->inventory", {k: after.get(k, 0) - before.get(k, 0) for k in after})
for s in report["per_second"]:
    print(f"  second {s['second']:2}: error rate {s['error_rate']}, p95 {s['p95']} ms")
