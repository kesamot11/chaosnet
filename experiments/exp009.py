"""EXP-009 (#161): the healthy lab with tracing on and off, interleaved.

    python3 experiments/exp009.py backend lab 5

For each of N pairs: tracing off (LAB_TRACING_ENDPOINT empty) then on, the services
recreated with that setting, 5 s of warm-up load, then 20 s at 50 req/s. Prints p50 and
p95 of every run and the medians per setting.
"""

import json
import os
import statistics
import subprocess
import sys

BACKEND, LAB, PAIRS = sys.argv[1], sys.argv[2], int(sys.argv[3])
SERVICES = ["gateway", "orders", "inventory"]


def lab(tracing: bool) -> None:
    env = dict(os.environ)
    if tracing:
        env.pop("LAB_TRACING_ENDPOINT", None)
    else:
        env["LAB_TRACING_ENDPOINT"] = ""
    subprocess.run(["docker", "compose", "up", "-d", "--wait", *SERVICES], cwd=LAB, env=env,
                   check=True, capture_output=True)


def load(seconds: int) -> dict:
    out = subprocess.run(
        ["uv", "run", "python", "-m", "chaosnet.loadgen", "http://127.0.0.1:8080/orders",
         "--rate", "50", "--duration", str(seconds)],
        cwd=BACKEND, capture_output=True, text=True, check=True,
    ).stdout
    return json.loads(out)


results: dict[bool, list[tuple[float, float]]] = {False: [], True: []}
for pair in range(PAIRS):
    for tracing in (False, True):
        lab(tracing)
        load(5)  # warm-up: connections, caches
        report = load(20)
        lat = report["latency_ms"]["all"]
        ok = report["outcomes"].get("ok", 0)
        results[tracing].append((lat["p50"], lat["p95"]))
        print(f"pair {pair + 1} tracing {'on ' if tracing else 'off'}: "
              f"p50 {lat['p50']:6.2f} ms  p95 {lat['p95']:6.2f} ms  ok {ok}/{report['scheduled']}")
for tracing in (False, True):
    p50s = [r[0] for r in results[tracing]]
    p95s = [r[1] for r in results[tracing]]
    print(f"tracing {'on ' if tracing else 'off'}: median p50 {statistics.median(p50s):.2f} ms "
          f"[{min(p50s):.2f} – {max(p50s):.2f}], median p95 {statistics.median(p95s):.2f} ms")
