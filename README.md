# ChaosNet

An interactive laboratory for building, running, observing and deliberately
breaking real distributed systems and networks.

> **Status:** early development (Sprint 1). Nothing here is usable yet. See the
> [project board](https://github.com/users/kesamot11/projects/2) and
> [milestones](https://github.com/kesamot11/chaosnet/milestones).

ChaosNet measures real system behaviour. It never fabricates results.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Architecture decisions](docs/DECISIONS.md)
- [Learning log](docs/LEARNING.md)

## Development setup

Requirements:

- [uv](https://docs.astral.sh/uv/) (it installs the right Python, 3.14, for you)
- Docker with Compose v2+ (developed on Docker Desktop for Mac, Apple Silicon)
- `make`

```bash
git clone https://github.com/kesamot11/chaosnet.git
cd chaosnet/backend
uv sync          # creates .venv with Python 3.14 and dev tools from uv.lock
cd ..
make check       # lint, format check, type check, tests
```

`make fmt` applies formatting and safe lint fixes.

## Running the demo lab

A small distributed system, `gateway -> orders -> inventory`, that experiments run
against. Only the gateway is reachable from the host.

```bash
cd lab
docker compose up -d --build --wait
curl -X POST localhost:8080/orders
docker compose down
```

The lab is generated from `lab/topology.json`: its services, the links between them,
and each link's timeout and retries. The controller (`chaosnet-api`, below) applies it
when it starts, and the UI's editor changes and applies it on Save. Without the
controller, generate the lab again after changing the file and restart it (no rebuild:
every service runs the same program):

```bash
cd backend && uv run chaosnet-lab
```

Set `ENTRY_PORT` if 8080 is taken.

A link can also have `"backoff_s"` (wait before a retry, doubled each time, with jitter)
and `"breaker": true` (a circuit breaker at the caller: above 50 % failures in 10 s,
with at least 10 calls, it answers `503 circuit_open` at once for 5 s, then lets one
trial call through; ADR-008) and `"fallback": true` (when the callee fails, the caller
answers without it, with `{"fallback": "<hop>"}` in its place; never on a 4xx; ADR-010).
The generator warns when a link times out before the
service it calls may answer.

Prometheus counts the requests every service received (`lab_requests_total`) and every
attempt on every link, with its outcome (`lab_attempts_total`), counted by the caller so
attempts to a hanging service are counted too. Query it at http://127.0.0.1:9090
(`PROMETHEUS_PORT` to change), e.g. `lab_attempts_total{hop="orders->inventory"}`.

Every request is traced (OpenTelemetry): one trace per request, with a span in every
service it passes, joined by the `traceparent` header. Open Jaeger at
http://127.0.0.1:16686 (`JAEGER_PORT` to change) and pick the service `gateway`.

Generate load against it (open model, so a slow lab cannot hide its latency):

```bash
cd backend
uv run python -m chaosnet.loadgen http://localhost:8080/orders --rate 20 --duration 10 \
    --body '{"item_id": "42"}'
```

Inject a fault for a fixed time (it is always removed at the end, on Ctrl+C and on `kill`):

```bash
cd backend
uv run chaosnet-fault latency --link orders-inventory --ms 300 --direction both --duration 60
uv run chaosnet-fault list     # active faults
uv run chaosnet-fault clear    # remove all faults
```

Links: `gateway-orders`, `orders-inventory`. Fault kinds: `latency`, `bandwidth`, `reset_peer`.

Run whole experiments (baseline, inject, recover, verdict) through the controller API,
on `127.0.0.1:8476` (`CHAOSNET_PORT`). Load always goes to the lab gateway (`TARGET_URL`):

```bash
cd backend
uv run chaosnet-api
curl -X POST localhost:8476/experiments -H 'content-type: application/json' -d '{
  "name": "orders-inventory +300 ms",
  "fault": {"kind": "latency", "link": "orders-inventory", "direction": "both", "ms": 300},
  "load": {"rate": 20, "body": {"item_id": "42"}},
  "phases_s": {"baseline": 10, "inject": 10, "recover": 10},
  "hypothesis": {"max_p95_ms": 500, "max_error_rate": 0.01}}'
curl localhost:8476/experiments/1
curl -X POST localhost:8476/experiments/1/abort
```

The UI (needs Node 26 and a running `chaosnet-api`):

```bash
cd frontend
npm ci --ignore-scripts
npm run dev        # http://127.0.0.1:5173
```

The UI shows the lab as a graph and is also its editor (ADR-011):

- drag a service to place it; positions are saved at once and don't restart the lab,
- add and remove services, draw a link from a service's right side to another's left
  side, select a link or a service and remove it,
- select a link to change its timeout, retries, backoff, retry budget, breaker and
  fallback, or to run an experiment on it,
- changes wait as a draft until **Save**, which applies them: the controller checks the
  topology, regenerates the lab, restarts it and waits until it answers. If the new lab
  doesn't start, the previous one comes back, with the reason. Save is refused while an
  experiment runs.

Every experiment records the topology it ran on and shows it with its results.

`make integration` runs the acceptance tests against a real Compose lab (needs Docker).

## License

[MIT](LICENSE)
