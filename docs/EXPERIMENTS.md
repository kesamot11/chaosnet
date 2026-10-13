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
