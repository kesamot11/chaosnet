# Sprint 7: review and retrospective

- **Dates:** 2026-11-04 to 2026-11-05
- **Goal:** follow one request through the lab with traces (M5), and use them in
  experiments.
- **Result:** goal met. 20/20 points. Epic M5 (#6) stays open for #173, added in the
  review.

## Review: what works (demonstrated)

| Issue | Outcome | Evidence |
|---|---|---|
| #156 ADR-009 | tracing with OpenTelemetry and Jaeger; M5 before the fallback (#145) | `docs/DECISIONS.md` |
| #157 Jaeger in the lab | the generated lab sends spans to Jaeger on `:16686` | integration test via the v3 API |
| #158 a span per attempt | `attempt n` with its outcome, `backoff` with its wait, `retry refused` and `circuit open` events | unit tests; Jaeger by hand |
| #159 trace from results | every phase links to its slowest failed request, else its slowest | `example_trace`, rule by Tomáš |
| #160 EXP-008 | A, B and an open breaker: **all three predictions correct** | `experiments/exp008.py` |
| #161 EXP-009 | tracing costs **+0.9 ms p50 (+14 %)**; the prediction "nothing" was wrong | 5 interleaved pairs |
| #99 progress bar | a bar for the running phase; "waiting for requests in flight" past its length; an honest "unknown" | PR #171; run by hand in the lab ("12 s of 15 s") |

Written by Tomáš:

- `example_trace`,
- `phaseProgress` and its tests,
- the change detection in `useExperiment`,
- the baseline start in `ExperimentForm`,
- every prediction.

Decided by Tomáš:

- M5 before the fallback,
- "the slowest failed, else the slowest",
- the phase start in `localStorage` instead of a DB column,
- an honest message instead of a made-up bar,
- the baseline start written by the page that starts the experiment,
- keeping M5 open for #173 (click the latency chart to open a trace) rather than
  exemplars in Prometheus.

Found by Tomáš: with a single request the breaker never opens; EXP-008 needed load to
open it first.

Found by measuring or running:

- a trace shows abandoned work in one request: in B the orders spans outlive their
  parents,
- an open breaker leaves almost nothing in a trace; without the `circuit open` event a
  5 ms failure would be a mystery,
- creating spans costs time, exporting them doesn't,
- the manual run of #99 found that a baseline started from the form looked "unknown"
  (the runner leaves `pending` before the first poll), and that a refresh forgets the
  running experiment (#172),
- Node 25+ hides jsdom's `localStorage` in tests.

Claude's mistakes:

- an integration test assumed Jaeger's v1 API (404 in 2.22),
- middleware added after startup (caught by the tests),
- referred to "#158" without saying what it was,
- chose variant A of #99's design for Tomáš; he corrected it and chose otherwise.

## Retrospective

**What helped most:** thinking it through and filling in the `???` skeletons; help
with syntax when the core logic was right.

**What was hardest:** writing code from scratch.

**Self-rated understanding of Sprint 7 code:** 3.5–4/5 (Sprint 6: 3.5).

**Interview check:**

- Quiz: 6/8, with options of similar length and the answers spread over A–D.
  - Missed: where tracing's 0.9 ms comes from. Answered Toxiproxy, which was present in
    both variants, so it can't explain the difference.
  - Missed: `example_trace`'s choice. He misread "timeout" as "ok"; it is his own rule.
- Own words:
  - **Backoff:** now right that it grows (the Sprint 6 weak spot), but described as
    +0.1 s per retry instead of doubling, and as 4 waits instead of 3.
  - **Metrics vs traces:** chose correctly between Prometheus and Jaeger; the "why"
    needed refining: metrics say *that* and *how much*, a trace says *where* and *why*.
  - **#99's design:**
    - right that `created_at` plus the earlier phases drifts with the drain wait,
    - said `updated_at` may be null (it can't be); the real problem is that it also
      changes when a result is saved.

## Actions for Sprint 8

1. Skeletons with `???` by default; Tomáš fills the logic, syntax comes ready.
2. Revisit exponential backoff once more (doubling, one wait per retry).
3. Candidates: #173 (chart → trace, completes M5), #172 (refresh), #145 (fallback).
