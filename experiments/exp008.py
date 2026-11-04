"""EXP-008 (#160): the trace of one request with inventory paused, as a tree.

    python3 experiments/exp008.py lab [--open-breaker]

Pauses inventory, sends one request (with --open-breaker, first 20 requests at once to
open the breaker on orders -> inventory), unpauses after 3 s so abandoned attempts
reach inventory, then prints the latest gateway trace from Jaeger: every span with its
start and length relative to the request, attempt numbers, outcomes and events.
"""

import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

LAB = sys.argv[1]
JAEGER = "http://127.0.0.1:16686/api/v3/traces"


def compose(*args: str) -> None:
    subprocess.run(["docker", "compose", *args], cwd=LAB, check=True, capture_output=True)


def order() -> tuple[int, float]:
    start = time.perf_counter()
    req = urllib.request.Request("http://127.0.0.1:8080/orders", method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            code = r.status
    except urllib.error.HTTPError as e:
        code = e.code
    return code, time.perf_counter() - start


def attrs(items: list[dict]) -> dict:
    return {a["key"]: next(iter(a["value"].values())) for a in items or []}


compose("pause", "inventory")
try:
    if "--open-breaker" in sys.argv:
        with ThreadPoolExecutor(20) as pool:
            list(pool.map(lambda _: order(), range(20)))
        time.sleep(0.5)
    code, elapsed = order()
    print(f"request: {code} in {elapsed:.3f} s")
    time.sleep(3)
finally:
    compose("unpause", "inventory")
time.sleep(3)  # abandoned attempts reach inventory; spans are exported

now = datetime.now(timezone.utc)
params = urllib.parse.urlencode({
    "query.service_name": "gateway",
    "query.start_time_min": (now - timedelta(minutes=1)).isoformat(),
    "query.start_time_max": now.isoformat(),
    "query.num_traces": 1,
})
data = json.load(urllib.request.urlopen(f"{JAEGER}?{params}"))
spans = []
for rs in data["result"]["resourceSpans"]:
    service = attrs(rs["resource"]["attributes"]).get("service.name")
    for scope in rs["scopeSpans"]:
        for s in scope["spans"]:
            if s["name"].endswith("http send") or s["name"].endswith("http receive"):
                continue  # ASGI internals
            spans.append({**s, "service": service})
by_id = {s["spanId"]: s for s in spans}
t0 = min(int(s["startTimeUnixNano"]) for s in spans)


def depth(s: dict) -> int:
    d, p = 0, s.get("parentSpanId")
    while p in by_id:
        d, p = d + 1, by_id[p].get("parentSpanId")
    return d


for s in sorted(spans, key=lambda s: int(s["startTimeUnixNano"])):
    start = (int(s["startTimeUnixNano"]) - t0) / 1e9
    length = (int(s["endTimeUnixNano"]) - int(s["startTimeUnixNano"])) / 1e9
    a = attrs(s.get("attributes", []))
    extra = " ".join(f"{k.split('.')[-1]}={a[k]}" for k in ("chaosnet.attempt", "chaosnet.outcome") if k in a)
    events = " ".join(f"[{e['name']}]" for e in s.get("events", []))
    print(f"{'  ' * depth(s)}{s['service']}: {s['name']:<22} {start:7.3f} s  +{length:6.3f} s  {extra} {events}")
