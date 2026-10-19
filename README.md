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
curl -X POST localhost:8080/orders -H 'content-type: application/json' -d '{"item_id": "42"}'
docker compose down
```

Per-hop timeouts and retries are environment variables (see `lab/compose.yaml`),
e.g. `ORDERS_MAX_RETRIES=0 docker compose up -d --wait`. Set `GATEWAY_PORT` if 8080
is taken.

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

`make integration` runs the acceptance tests against a real Compose lab (needs Docker).

## License

[MIT](LICENSE)
