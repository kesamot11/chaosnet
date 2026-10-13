# Experiments

Every experiment records its prediction *before* the first run, then the real
measurements, then what the difference teaches. Numbers in this file come from
actual runs; nothing is estimated after the fact.

## Template

- **Question / hypothesis:** what we expect and why
- **Prediction:** written down before measuring
- **Setup:** versions, configuration, environment
- **Method:** exact commands, repetitions, what is discarded
- **Results:** raw per-run numbers and their spread
- **Interpretation:** prediction vs. reality
- **Limitations:** what the numbers do *not* show

---

## EXP-001: Healthy baseline (#15)

**Question:** how does the healthy lab (`gateway -> orders -> inventory`, no faults)
behave under steady load, how much do runs differ from each other, and how much
latency does Docker Desktop's port forwarding add when measuring from the Mac?

**Prediction (Tomáš, 2026-10-13, before any run):**

1. Measured from the Mac at 50 req/s: p50 ≈ 20 ms, p99 ≈ 100 ms.
2. Measuring from inside the Docker network is faster, because the Mac → VM
   forwarding overhead disappears.
3. With 1500 samples per run, runs will not differ much.

**Setup:**

- Lab from `lab/compose.yaml` at commit `e02dfe1` (orders→inventory: 0.5 s timeout,
  2 retries; gateway→orders: 2.0 s, 1 retry), freshly restarted before measuring.
- Load generator `chaosnet.loadgen` from #14.
- Apple Silicon Mac, macOS 26.6; Docker Desktop 4.95.0, VM with 10 CPUs and 7.7 GiB;
  other Mac applications running as usual (not a quiet machine).

**Method:** 50 req/s for 30 s (1500 requests per run), per-request timeout 5 s,
`POST /orders {"item_id": "42"}`. One warm-up run from the Mac (discarded), then 5
runs from the Mac and 5 runs from a container attached to the lab network:

```bash
# from the Mac, through the published port
cd backend && uv run python -m chaosnet.loadgen http://127.0.0.1:8080/orders \
    --rate 50 --duration 30 --timeout 5 --body '{"item_id":"42"}'

# from inside the lab network (same generator code, lab image provides httpx)
docker run --rm --network chaosnet-lab_default -v "$PWD/backend/src:/src:ro" \
    -e PYTHONPATH=/src chaosnet-lab:dev python -m chaosnet.loadgen \
    http://gateway:8000/orders --rate 50 --duration 30 --timeout 5 --body '{"item_id":"42"}'
```

**Results** (latency of `ok` requests in ms; all 16 500 requests were `ok`, none dropped):

| run | p50 | p95 | p99 | max | send lag p50 / max |
|---|---|---|---|---|---|
| Mac warm-up (discarded) | 4.56 | 10.55 | 13.46 | 57.57 | 1.08 / 45.81 |
| Mac 1 | 5.19 | 10.06 | 17.07 | 91.40 | 1.09 / 41.97 |
| Mac 2 | 4.86 | 10.31 | 12.13 | 38.59 | 1.08 / 14.63 |
| Mac 3 | 4.63 | 10.99 | 11.90 | 40.23 | 1.08 / 10.40 |
| Mac 4 | 4.71 | 10.50 | 12.23 | 39.48 | 1.08 / 10.06 |
| Mac 5 | 4.96 | 11.36 | 12.53 | 36.21 | 1.08 / 10.55 |
| network 1 | 8.76 | 12.38 | 13.67 | 18.57 | 2.61 / 6.35 |
| network 2 | 8.77 | 12.49 | 13.87 | 30.10 | 2.53 / 6.31 |
| network 3 | 8.69 | 12.35 | 13.77 | 27.08 | 2.56 / 15.26 |
| network 4 | 8.92 | 12.21 | 13.58 | 22.84 | 2.61 / 11.95 |
| network 5 | 8.74 | 12.29 | 13.57 | 15.84 | 2.63 / 6.69 |

Median across the 5 runs [min – max]:

| | p50 | p95 | p99 | max |
|---|---|---|---|---|
| from the Mac | 4.86 [4.63 – 5.19] | 10.50 [10.06 – 11.36] | 12.23 [11.90 – 17.07] | 39.48 [36.21 – 91.40] |
| from the network | 8.76 [8.69 – 8.92] | 12.35 [12.21 – 12.49] | 13.67 [13.57 – 13.87] | 22.84 [15.84 – 30.10] |

**Interpretation:**

1. *Prediction p50 ≈ 20 ms, p99 ≈ 100 ms:* reality was 4.9 ms and 12.2 ms, about
   4–8x faster than predicted. Three in-memory services on one machine are fast.
2. *Prediction "faster from inside the network":* **wrong.** From inside, p50 was
   **slower** (8.8 vs 4.9 ms), though the tail was tighter (max 16–30 ms vs
   36–91 ms). Part of the gap is the generator itself: latency is measured from
   the scheduled send time, and the generator sends later inside the VM (send lag
   p50 2.6 ms vs 1.1 ms on the Mac). That explains ~1.5 ms of the ~3.9 ms
   difference. Unverified hypothesis for the rest: the generator competes for VM
   CPU with the services it measures. Port forwarding, which the prediction was
   about, does not show up as a measurable cost.
3. *Prediction "runs will not differ much":* **right for p50–p99** (p95 spread
   10.1–11.4 ms). **Not for max**: 36–91 ms on the Mac. The maximum is a single
   sample and is too noisy to compare experiments with.

**Decision for measuring from the Mac (decision 2a in #14): keep it.** Faults we
will inject change latency by hundreds of milliseconds; the healthy p99 is ~12 ms
and runs agree within ~1–5 ms up to p99. Compare experiments on p50/p95/p99, never
on max. Revisit if an experiment cares about effects below ~50 ms in the tail.

**Limitations:**

- Every latency includes the generator's own send lag (~1.1 ms on the Mac) by
  design; absolute numbers are slightly pessimistic.
- One machine, one evening, normal desktop activity. Not a benchmark of the
  services, only a reference for later experiments on the same setup.
- Emulated network inside one VM: no physical links, so these numbers say
  nothing about real network latency.
- One request type, constant rate, warm caches; no bursts.

### EXP-001b: baseline with Toxiproxy in the path (#30)

**Question:** how much latency do the two proxy hops (gateway→Toxiproxy→orders,
orders→Toxiproxy→inventory, no toxics) add to the healthy baseline?

**Method:** same as EXP-001 from the Mac (warm-up + 5 runs, 50 req/s × 30 s), same
day, lab freshly restarted with Toxiproxy 2.12.0 in the path.

| | p50 | p95 | p99 | max |
|---|---|---|---|---|
| EXP-001, no proxy | 4.86 [4.63 – 5.19] | 10.50 [10.06 – 11.36] | 12.23 [11.90 – 17.07] | 39.48 [36.21 – 91.40] |
| with proxy | 4.79 [4.69 – 4.96] | 11.10 [10.56 – 11.56] | 12.41 [11.99 – 12.79] | 39.02 [38.53 – 39.83] |

All 7500 requests `ok`. Generator send lag max ≤ 10.3 ms.

**Interpretation:** no measurable overhead. Every percentile with the proxy lies
inside the run-to-run spread of EXP-001. The proxy cost is smaller than the noise
of this setup; EXP-001b is the baseline for fault experiments from now on.

**Limitations:** the two baselines were measured about an hour apart, not
interleaved, so slow drift of the machine would be indistinguishable from a small
proxy effect.
