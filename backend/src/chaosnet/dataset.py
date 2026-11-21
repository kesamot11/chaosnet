"""Labelled runs for machine learning (#254, ADR-013): every fault, on every link, a few times.

Each run is a whole experiment through the controller. Its seconds are labelled by what was
done, not by what was measured: a second of the inject phase is a fault on the run's link,
every other second is normal. The numbers per link come from the lab's Prometheus.

    uv run chaosnet-dataset ../data/runs.csv
"""

import csv
import sys
import time
from typing import Any

import httpx

CONTROLLER = "http://127.0.0.1:8476"
PROMETHEUS = "http://127.0.0.1:9090"
LINKS = ["gateway-orders", "orders-inventory"]
# The strengths Tomáš chose (#254): weak ones only slow a link, strong ones break it.
FAULTS: list[dict[str, Any]] = [
    *({"kind": "latency", "ms": ms} for ms in (25, 100, 200, 500)),
    *({"kind": "bandwidth", "kbps": kbps} for kbps in (64, 16, 4, 1)),
    {"kind": "reset_peer"},  # one strength: a share of connections is all or nothing (#254)
]
REPEATS = 3
PHASES_S = {"baseline": 10, "inject": 15, "recover": 10}
OUTCOMES = ["ok", "http_error", "timeout", "connection_error", "rejected"]
WINDOW = "3s"  # rate() needs two scrapes; at one scrape a second, 3 s always holds them
# Per link and second: attempts by outcome, and how long they took (p50, p95).
QUERIES = {
    "attempts": f"sum by (hop, outcome) (rate(lab_attempts_total[{WINDOW}]))",
    "p50_ms": "1000 * histogram_quantile(0.5, sum by (le, hop) "
    f"(rate(lab_attempt_duration_seconds_bucket[{WINDOW}])))",
    "p95_ms": "1000 * histogram_quantile(0.95, sum by (le, hop) "
    f"(rate(lab_attempt_duration_seconds_bucket[{WINDOW}])))",
}
FEATURES = [f"{link} {name}" for link in LINKS for name in [*OUTCOMES, "p50_ms", "p95_ms"]]
COLUMNS = ["run", "second", "phase", "kind", "strength", "fault", "fault_link", *FEATURES]


def run_one(client: httpx.Client, link: str, fault: dict[str, Any]) -> tuple[int, dict[str, float]]:
    """Start one experiment and wait for its end; return its id and when each phase began."""
    spec = {
        "name": f"dataset {fault['kind']} {fault.get('ms') or fault.get('kbps') or ''} {link}",
        "fault": {**fault, "link": link, "direction": "both"},
        "load": {"rate": 20, "body": {"item_id": "42"}},
        "phases_s": PHASES_S,
        "hypothesis": {"max_p95_ms": 500, "max_error_rate": 0.01},
    }
    res = client.post(f"{CONTROLLER}/experiments", json=spec)
    res.raise_for_status()
    run_id: int = res.json()["id"]
    began: dict[str, float] = {}
    while True:  # ponytail: polled every 0.2 s, so a phase starts up to 0.2 s later than here
        state = client.get(f"{CONTROLLER}/experiments/{run_id}").json()["state"]
        began.setdefault(state, time.time())
        if state in ("completed", "failed", "aborted"):
            break
        time.sleep(0.2)
    if state != "completed":
        raise RuntimeError(f"experiment {run_id} ended {state}")
    return run_id, began


def features(client: httpx.Client, start: float, end: float) -> dict[int, dict[str, float]]:
    """The numbers per link for every whole second from start to end, by its unix time."""
    seconds: dict[int, dict[str, float]] = {}
    for name, query in QUERIES.items():
        res = client.get(
            f"{PROMETHEUS}/api/v1/query_range",
            params={"query": query, "start": start, "end": end, "step": 1},
        )
        res.raise_for_status()
        for series in res.json()["data"]["result"]:
            link = series["metric"]["hop"].replace("->", "-")
            column = f"{link} {series['metric']['outcome'] if name == 'attempts' else name}"
            for t, value in series["values"]:
                seconds.setdefault(int(t), {})[column] = float(value)
    return seconds


def rows(
    run_id: int,
    link: str,
    fault: dict[str, Any],
    began: dict[str, float],
    numbers: dict[int, dict[str, float]],
) -> list[dict[str, Any]]:
    """One row a second, labelled by the phase it fell in (what was done, not what was seen)."""
    out: list[dict[str, Any]] = []
    for second, t in enumerate(sorted(numbers)):
        phase = (
            "recover" if t >= began["recover"] else "inject" if t >= began["inject"] else "baseline"
        )
        faulty = phase == "inject"
        out.append(
            {
                "run": run_id,
                "second": second,
                "phase": phase,
                "kind": fault["kind"],
                "strength": fault.get("ms") or fault.get("kbps") or "",
                "fault": int(faulty),
                "fault_link": link if faulty else "",
                # NaN when a link had no attempts that second (p50, p95): left empty
                **{c: v for c, v in numbers[t].items() if v == v},
            }
        )
    return out


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "../data/runs.csv"
    plan = [(link, fault) for _ in range(REPEATS) for fault in FAULTS for link in LINKS]
    with httpx.Client(timeout=10) as client, open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, COLUMNS, restval="")
        writer.writeheader()
        for i, (link, fault) in enumerate(plan, 1):
            run_id, began = run_one(client, link, fault)
            time.sleep(2)  # the last seconds reach Prometheus
            numbers = features(client, began["baseline"], began["completed"])
            writer.writerows(rows(run_id, link, fault, began, numbers))
            f.flush()  # a stopped script keeps the runs it finished
            print(f"{i}/{len(plan)} experiment {run_id}: {fault} on {link}", flush=True)
