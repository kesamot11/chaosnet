"""EXP-004 (#118): N sequential requests with inventory paused; counts from Prometheus.

    python3 experiments/exp004.py 10 lab

Needs the lab running (Prometheus on 127.0.0.1:9090, gateway on 8080). Standard
library only, so it runs without any project's environment.
"""

import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

N = int(sys.argv[1]); LAB = sys.argv[2]
PROM = "http://127.0.0.1:9090/api/v1/query?query="

def q(query):
    with urllib.request.urlopen(PROM + urllib.parse.quote(query)) as r:
        res = json.load(r)["data"]["result"]
    return {json.dumps(x["metric"], sort_keys=True): float(x["value"][1]) for x in res}

def snapshot():
    time.sleep(2.5)
    return {**q("lab_requests_total"), **q("lab_attempts_total")}

def compose(*a):
    subprocess.run(["docker", "compose", *a], cwd=LAB, check=True, capture_output=True)

before = snapshot()
compose("pause", "inventory")
lat, codes, hops = [], [], []
try:
    for _ in range(N):
        t = time.perf_counter()
        req = urllib.request.Request("http://127.0.0.1:8080/orders", method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                codes.append(r.status); body = json.load(r)
        except urllib.error.HTTPError as e:
            codes.append(e.code); body = json.load(e)
        lat.append(time.perf_counter() - t); hops.append(body.get("failed_hop"))
finally:
    compose("unpause", "inventory")
time.sleep(5)  # let orders finish attempts the gateway gave up on
after = snapshot()
delta = {k: after.get(k, 0) - before.get(k, 0) for k in after if after.get(k, 0) != before.get(k, 0)}
for k, v in sorted(delta.items()): print(f"{v:6.0f}  {k}")
lat.sort()
print("codes", {c: codes.count(c) for c in set(codes)}, "failed_hop", {h: hops.count(h) for h in set(hops)})
print(f"latency s: min {lat[0]:.3f} median {lat[len(lat)//2]:.3f} max {lat[-1]:.3f}")
