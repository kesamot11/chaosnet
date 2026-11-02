# Sprint 6: review and retrospective

- **Dates:** 2026-10-31 to 2026-11-02
- **Goal:** a circuit breaker and a retry budget, measured against the storm.
- **Result:** goal met. 20/20 points; epic M6 (#7) done; **released as v0.2.0**, the
  first release.

## Review: what works (demonstrated)

| Issue | Outcome | Evidence |
|---|---|---|
| #134 ADR-008 | breaker and budget decisions | `docs/DECISIONS.md` |
| #135 breaker | closed / open / half-open, 10 s window, minimum of 10, one trial | 10 tests, one per arrow of the drawing |
| #136 breaker in the service | `"breaker": true`; `503 circuit_open` at once; `rejected` counted | integration on a generated lab |
| #137 EXP-006 | 1 200 attempts → 126; 1.5 s → ~10 ms; no request saved | `experiments/exp006.py`, prediction correct |
| #138 retry budget | token bucket per link, starts full | unit tests incl. a storm |
| #139 EXP-007 | 2 400 attempts → 500; median 2.0 s → 0.5 s | `experiments/exp007.py`, load prediction correct |

Written by Tomáš: what the breaker remembers, `Breaker.allow` and `record`; the retry
budget's design (shared per link, 1 retry per 10 first attempts, cap 10, start full)
and `RetryBudget`. Decisions by Tomáš: the opening rule (a rate, not a count in a row;
with a minimum), an error that names the cause, the fallback (#145) out of this sprint,
the release. Found by Tomáš: an initial flood the breaker cannot stop (it needs
evidence); a quiz whose answers were given away by their length.

Found by measuring: a breaker closes only through traffic; at low traffic it may never
open; a budget on the inner link makes the inner service answer before the outer
timeout again (EXP-007's latency beat the prediction).

Claude's mistakes:

- two breaker tests wrong at first (fixed before handing over),
- an EXP-006 script that did not close the breaker between runs (two runs discarded),
- an EXP-007 run discarded: the restart reset the counters before the "before" snapshot,
- printed only a summary line when an integration run failed, so which test is unknown,
- `gh release create` with a short SHA (rejected by GitHub),
- a quiz with the right answer always the longest and nearly always B.

## Retrospective

**What helped most:** the explanations.

**What was hardest:** nothing in particular this time.

**Self-rated understanding of Sprint 6 code:** 3.5/5 (Sprint 5: 3–4).

**Interview check:** quiz 10/10, discounted (the length of the answers gave them away).
Own words: jitter vs backoff now right for jitter (the Sprint 5 weak spot); backoff
still described as a fixed wait (it grows). Breaker vs budget: good intuition, refined:
the budget limits retries, the breaker all calls, and they complement each other.

## Actions for Sprint 7

1. Quizzes: options of similar length, the right answer spread over A–D, every config
   stated.
2. Next milestone: M5 (tracing) or the fallback (#145); decide in planning.
