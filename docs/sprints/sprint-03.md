# Sprint 3: review and retrospective

- **Dates:** 2026-10-17 to 2026-10-18
- **Goal:** one `POST /experiments` runs a whole experiment (baseline → inject →
  recover), stores the results and a verdict, and an experiment interrupted by a
  controller crash ends as `aborted`.
- **Result:** goal met. 24/24 points; epic M3 (#4) closed. #62 (latency over time) moved
  to M4.

## Review: what works (demonstrated)

| Issue | Outcome | Evidence |
|---|---|---|
| #50 state machine | allowed transitions as a table; end states have no way out | 36 unit tests |
| #51 SQLite store | records survive a reopen; one running experiment at a time | unit tests |
| #52 runner | fault active exactly during the inject measurement; always removed | 7 unit tests |
| #53 verdict | p95 and error rate against the hypothesis, with reasons | EXP-002 numbers as tests |
| #54 HTTP API | start, list, get, abort; `409` while one runs; `127.0.0.1` only | 8 tests + real lab |
| #55 reconcile | after `kill -9` and restart: `aborted`, "controller restarted during inject" | unit + integration tests |
| #56 integration tests | end to end, `409` and `kill -9` against the real lab, in CI | 15 integration tests |
| #57 ADR-004 | 8 decisions, one amending ADR-001 layer 2 | `docs/DECISIONS.md` |
| #58 EXP-003 | the controller measures the same as the manual method | `docs/EXPERIMENTS.md` |

Written by Tomáš: the transition table, `judge`, `Runner._inject` and `reconcile`, the
last one designed by him first (plan in words, then code). Review findings by Tomáš: a
missing API test for failed experiments (#64); his question about `TARGET_URL` led to the
trust-boundary reasoning in ADR-004. Decisions by Tomáš: all five planning decisions,
the fixed load target, `remove_all` in reconcile, "investigate now" in EXP-003, which
turned "the controller measures differently" into "the machine drifted".

Claude's mistakes:

- handed over `_inject` as a numbered list of steps, so Tomáš only translated it into
  syntax,
- explained "`__init__` is the toolbox", which confused him on `FaultDriver`,
- said "next to" instead of "below" for an import,
- wrote an integration test that subtracted two p95s (flaky, fixed before merge),
- compared the controller and the manual method without interleaving them (EXP-003,
  found by the investigation).

## Retrospective

**What helped most:** writing the code himself, and above all designing the whole
solution himself (`reconcile`).

**What was hardest:** writing code from nothing, with no scaffold at all.

**Self-rated understanding of Sprint 3 code:** 3/5.

**Interview check:** quiz 10/10; own words 4 questions, weak spot: what removes the
fault after a controller crash (the watchdog, within ~5 s, not the restart). Details in
`docs/LEARNING.md`.

## Actions for Sprint 4

1. **Design before syntax** for every task Tomáš writes: Claude gives the goal and the
   scenarios that can go wrong, never the steps. Tomáš writes the plan in words, Claude
   reviews it, then he codes.
2. **Syntax is not the test.** Before he codes, Claude shows the tricky constructs on a
   *different* example (as with the traffic-light table in #50): `try`/`except`
   placement, imports, `await`. Syntax hints are free; the logic stays his.
3. Run `make check` before the tests: pyright found the missing `await`s first.
4. Understanding 3/5 again: the interview check shows where the gaps are, then a
   teach-back of the Claude-written parts (`api.py`, `Runner.run`, the store) before
   Sprint 4 planning.
