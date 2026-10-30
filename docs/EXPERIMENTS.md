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

---

## EXP-002: +300 ms latency on orders → inventory (#36)

**Question:** how does a slow inventory link affect users, and how does the per-attempt
timeout (0.5 s, 2 retries on that hop) interact with the extra latency?

**Variants:**

- **A:** +300 ms in the request direction only (`--direction request`)
- **B:** +300 ms in both directions (`--direction both`)

**Prediction (Tomáš, 2026-10-15, before any measurement, recorded verbatim):**

| | p50 | errors |
|---|---|---|
| A | about 305 ms | none |
| B | 605 ms | all, 504 |

**Setup:** lab at `cd03c01` (Toxiproxy on both links, watchdog), `orders → inventory`
0.5 s per attempt and 2 retries (GET); `gateway → orders` 2.0 s, 1 retry. Fault applied
with `chaosnet-fault latency --link orders-inventory --ms 300 --direction <A|B>` for the
whole measurement, then removed (verified: 0 faults left after each variant).

**Method:** per variant one warm-up run (discarded) and 5 runs of 50 req/s × 30 s from the
Mac, as in EXP-001. Started 2026-10-15 13:02 UTC, after the prediction PR (#45) was opened.

**Results** (latency of all requests, ms; median across 5 runs [min – max]):

| | p50 | p95 | p99 | errors |
|---|---|---|---|---|
| EXP-001b, no fault | 4.79 | 11.10 | 12.41 | 0 / 7500 |
| **A**, +300 ms request | **306.9** [306.5 – 307.4] | 311.6 [311.3 – 312.0] | 313.5 [312.7 – 314.5] | **0 / 7500** |
| **B**, +300 ms both | **1509.6** [1509.6 – 1509.8] | 1513.8 [1513.1 – 1514.3] | 1520.5 [1519.0 – 1521.6] | **7500 / 7500**, all 504 |

Variant B status checked with a single request under the same fault:
`{"error":"timeout","failed_hop":"orders->inventory"}  HTTP 504 in 1.53 s`.
Generator send lag max ≤ 9.5 ms in every run.

**Interpretation:**

- *A:* predicted ~305 ms, no errors. **Correct.** 300 ms one-way stays below the 0.5 s
  per-attempt timeout, so every request succeeds, just 302 ms slower than baseline.
- *B errors:* predicted all 504. **Correct.** 600 ms round trip exceeds 0.5 s on every
  attempt.
- *B p50:* predicted 605 ms. **Wrong:** 1509.6 ms. The two B predictions contradicted
  each other: if no attempt answers within 0.5 s, orders makes all 3 attempts and gives up
  after 3 × 0.5 s = 1.5 s. Users wait 1.5 s *and* get an error.
- **Timeouts create a cliff.** Adding 300 ms on the return path turned "everything works,
  300 ms slower" into "nothing works". Degradation is not proportional to the fault.
- **Hypothesis, not measured:** in B every attempt reaches inventory and is processed;
  only the answer arrives too late. Inventory would do 3× the work (150 req/s instead of
  50) for zero successful requests. To verify with service metrics (M5); this is the
  retry amplification M6 is about.

**Limitations:** constant latency without jitter, so the cliff is perfectly sharp; with
jitter some attempts would succeed near the boundary. One request type, one machine.

## EXP-003: EXP-002 A through the controller (#58)

**Question:** does the experiment controller measure the same as the manual method
(fault CLI + load generator)? Before trusting its numbers, re-run a known experiment.

**Prediction (Tomáš, 2026-10-18, before any measurement, translated from Czech):**
"It should be the same, because the controller only automates what was done by hand."
Same means: inject p50 within **306.9 ± 5 ms** (301.9 – 311.9 ms).

**Setup:** lab and controller at `60f69a6` (no code change since `01d8346`), same hop
timeouts and retries as EXP-002. Fault: +300 ms latency, `orders-inventory`, direction
`request` (as EXP-002 A). All load from the Mac at 50 req/s, `--timeout 5`.

**Method:** 5 experiments through `POST /experiments`, each with baseline 30 s, inject
30 s, recover 30 s (2026-10-18 13:27–13:35 UTC, after the prediction PR #67 was merged).
The baseline phase precedes inject, so it takes the place of EXP-002's discarded
warm-up run. Latency of all requests, ms, median across runs [min – max].

**Results:** all 22 500 requests `ok`; 0 toxics left after every run; every verdict passed.

| | p50 | p95 | p99 |
|---|---|---|---|
| EXP-002 A, inject, manual (2026-10-15) | 306.9 [306.5 – 307.4] | 311.6 [311.3 – 312.0] | 313.5 [312.7 – 314.5] |
| **EXP-003, inject, controller** | **305.2** [305.2 – 305.9] | 306.4 [306.3 – 307.3] | 307.4 [307.1 – 308.2] |
| EXP-003, baseline, controller | 4.49 [4.46 – 5.38] | 5.57 [5.48 – 6.25] | 6.93 [6.67 – 7.37] |
| EXP-003, recover, controller | 4.55 [4.49 – 5.45] | 6.35 [6.06 – 6.92] | 7.28 [6.88 – 7.53] |

**Prediction:** inject p50 within 306.9 ± 5 ms. **Correct:** 305.2 ms, −1.7 ms.

**Investigation of the remaining difference.** The p95 was lower through the controller
in inject (306.4 vs 311.6) and in baseline (5.57 vs 11.10 in EXP-001b). Tomáš chose to
investigate before closing #58. Each check changed one thing; predictions are Tomáš's,
made before each run.

| # | Check (same day) | Prediction | Result |
|---|---|---|---|
| 1 | manual method again, inject (14:04–14:07, warm-up + 5 runs) | p50 closer to the controller's 305.2 than to 306.9 | **correct:** p50 305.7 [305.6 – 305.9], but p95 still 310.6 [310.1 – 311.2] |
| 2 | manual method, baseline (14:09–14:12) | none made | p95 11.89 [11.86 – 11.94], like EXP-001b, not like the controller |
| 3 | `localhost` (manual) vs `127.0.0.1` (controller), alternating 4 + 4 runs (14:22–14:26) | explains the whole difference | **wrong:** p95 11.79 vs 11.78 |
| 4 | one process, new client per run vs one shared client (as the controller), alternating 4 + 4 (14:27–14:32) | shared client faster | **wrong:** p95 11.82 vs 11.80 |
| 5 | controller and manual alternating, 3 + 3 runs (14:38–14:41) | none made | **same:** controller baseline p95 11.67 / 11.98 / 11.96, manual 11.86 / 11.76 / 11.03 |

**Interpretation:**

- **The controller measures the same as the manual method.** Run alternately, the two
  cannot be told apart (check 5).
- **The difference was time, not method.** The controller runs (13:27–13:35) were not
  interleaved with the manual ones (from 14:04). Between the two, the baseline p95 of
  the same lab doubled from ~5.6 to ~11.8 ms with no change to code or configuration.
  The cause of that drift is unknown (machine load, power state, Docker VM); it was not
  investigated.
- **Comparing two methods needs alternating runs.** Back-to-back blocks, even 30 minutes
  apart on the same day, can attribute machine drift to the method. Checks 1 and 2 alone
  pointed at the controller; only check 5 removed the confound.
- Two plausible causes were ruled out by measurement: name resolution (`localhost`) and
  connection reuse.

**Decision:** use the controller for experiments from now on. Compare results only
within one session, and alternate runs when the expected effect is a few ms (as already
decided in EXP-001 for effects below ~50 ms).

**Limitations:** checks 3–5 had 3–4 runs per arm; enough to rule out a 6 ms effect, not
a sub-millisecond one. No fault in checks 2–5, so the inject-phase p95 difference
(306.4 vs 310.6) is attributed to the same drift by analogy, not by its own
interleaved test.

## EXP-004: retry amplification (#117, #118)

**Question:** inventory hangs, so every call to it times out. How many requests reach
inventory for one request at the gateway, and how long does the user wait? Two
configurations of the gateway → orders link:

| | gateway → orders | orders → inventory | orders' budget |
|---|---|---|---|
| **A** (today's `topology.json`) | 2.0 s timeout, 1 retry | 0.5 s timeout, 2 retries | 3 × 0.5 = 1.5 s |
| **B** | **1.0 s** timeout, 1 retry | 0.5 s timeout, 2 retries | 1.5 s |

**Prediction (Tomáš, 2026-10-30, before any measurement, translated from Czech):**

- **A: 3 requests reach inventory, the user waits 1.5 s.** Orders gives up after its
  three attempts and answers 504 within the gateway's 2.0 s. An HTTP answer is never
  retried (`call_downstream` retries only connection failures and timeouts), so the
  gateway passes it on. *How this prediction came about:* the first answer was 6
  requests and 4 s (2 gateway attempts × 2.0 s); corrected after going back to the
  rule that an HTTP response is not retried.
- **B: 6 requests reach inventory, the user waits 2 s.** The gateway times out after
  1.0 s, before orders has finished, and tries again; orders does not know the gateway
  gave up and finishes its first three attempts as well. 2 attempts × 1.0 s.
- Claude's addition to check: in B the error names `gateway->orders`, hiding that
  inventory is the cause.
