# Sprint 8: review and retrospective

- **Dates:** 2026-11-05
- **Goal:** a fallback and EXP-010; finish M5 (#172, #173); release v0.3.0.
- **Result:** goal met. 18/18 points. Epic M5 (#6) closed; v0.3.0 released.

## Review: what works (demonstrated)

| Issue | Outcome | Evidence |
|---|---|---|
| #175 ADR-010 | a fallback leaves the missing part out and is counted as `degraded` | `docs/DECISIONS.md` |
| #145 fallback | `"fallback": true` on a link: on a callee's 5xx the caller answers anyway; never on 4xx | unit tests; the lab |
| #176 `degraded` | a new outcome, neither `ok` nor an error; the verdict and the error rate leave it out; its own UI column | load generator tests |
| #177 EXP-010 | a fallback saves requests but doesn't make them faster; with a breaker **9 ms** and **126** attempts instead of 1 200 | `experiments/exp010.py` |
| #173 chart → trace | a dot for every second of the latency chart opens that second's trace | PR #184; run by hand in the lab |
| #172 refresh | after a refresh the UI follows the newest experiment, running or last | PR #186; run by hand in the lab |
| #178 release | M5 closed with its deviation; **v0.3.0** | the GitHub release |

Written by Tomáš:

- `has_fallback` and the fallback branch in the lab service,
- the `example_trace` rule with `degraded`,
- the trace per second in `per_second`,
- `fetchExperiments` and `current ?? newest.id` in `App`,
- every prediction of EXP-010.

Decided by Tomáš:

- a fallback's answer is `degraded`: no error, but the outage stays visible,
- a dot per second in the chart, not a click on the line,
- one rule for the phase and for each second (reuse `example_trace`, not a copy),
- the list of experiments, not a new endpoint: the newest is the running one,
- after a refresh also show a finished experiment ("a refresh by mistake"),
- an experiment the user starts wins over a late list,
- the Jaeger address in `api.ts`, not in a component.

Found by Tomáš:

- why the breaker opened only after ~40 calls (a call counts once it has finished),
- in review: a component importing a constant from another component, a missing test
  for a record without `trace`, a fixed 50 ms wait in a test,
- the UI can't change a link's breaker, fallback, retries or timeout (#185).

Found by measuring or running:

- the first EXP-010 run read wrong Prometheus deltas after recreating the lab; it was
  discarded and the counters are now read from the services,
- the per-second trace crashed (`max()` of an empty list) when a second's requests had
  no trace ID; found by the tests.

Claude's mistakes:

- switched branches in Tomáš's working copy; a stale editor save then removed the
  `degraded` code, which had to be restored,
- pushed tests with `xfail` markers without asking,
- claimed a second's traced requests could never be empty,
- removed Tomáš's `worst_id` lines instead of pointing at the bug,
- a push failed silently because its error output was hidden.

## Retrospective

**What helped most:** thinking it through.

**What was hardest:** TypeScript syntax ("I just need to get used to it").

**Missed:** a nicer UI (planned for Sprint 10).

**Self-rated understanding of Sprint 8 code:** 3.5–4/5 (Sprint 7: 3.5–4).

**Interview check:**

- Quiz: 7/8 (Sprint 7: 6/8).
  - **Backoff right now**: doubling, three waits of at most 0.1, 0.2 and 0.4 s. The
    weak spot of Sprints 6 and 7 is gone.
  - Missed: why the first experiment of the list is the running one. Answered "the
    backend sorts running ones first"; it sorts by id only, and `Store.create`
    refuses a new experiment while one runs, so nothing newer can exist.
- Own words:
  - **Fallback and breaker:** right that a fallback alone still sends every attempt to
    the failed service; missing that the breaker makes the failure fast and the
    fallback makes it an answer (1.5 s and 1 200 attempts vs. 9 ms and 126).
  - **`degraded`:** right on both sides: as `ok` an outage shows 0 % errors; as an
    error the fallback would look useless.
  - **The race in #172:** right that the user's own experiment wins; refined: the
    effect sees the id from page load, the function in `set…` sees the current one.

## Actions for Sprint 9

1. Skeletons with `???` stay the default; new TypeScript syntax shown on a different
   example, one piece at a time. The editor is mostly TypeScript: practice.
2. Keep the manual run in the lab before every PR.
3. Candidates: the drag-and-drop topology editor; #185 (per-link settings in the UI).
