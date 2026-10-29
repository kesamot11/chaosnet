# Sprint 4: review and retrospective

- **Dates:** 2026-10-19 to 2026-10-29
- **Goal:** in the browser, see the lab, pick a link, run an experiment and watch the
  result; the lab is generated from one `topology.json`.
- **Result:** goal met. 31/31 points; epic M4 (#5) done.

## Review: what works (demonstrated)

| Issue | Outcome | Evidence |
|---|---|---|
| #71 ADR-005 | UI stack, generated lab, polling, React Flow | `docs/DECISIONS.md` |
| #72 topology spec | `topology.json` v1, every rule with a named error, cycles found | 23 unit tests |
| #74 `GET /topology` | links with `available`; unknown link is 422 before any load | API tests |
| #75 frontend | Vite, React, TypeScript strict, Biome, Vitest, in CI | `frontend` job, required |
| #76 topology view | the lab left to right; click a link to select it | component tests; real controller |
| #77 experiment form | start on the selected link; every answer shown, values kept | 23 tests; experiment #1 from the UI |
| #78 status | phase, per-phase p50/p95/error rate, verdict, Abort | hook tests broken on purpose; abort left no toxics |
| #62 per second | p50, p95, error rate for every second of a phase | 8 unit tests; real load run |
| #79 graph | p95 and error rate over time, phases marked | tests on a recorded real experiment; browser |
| #73 generated lab | `uv run chaosnet-lab`; one generic service; drift check | reproduces the hand-written `toxiproxy.json`; 13/13 integration |
| #80 branching | a branch run for real: both called at the same time | +300 ms on both → +~300 ms (+607 ms when made sequential) |

Written by Tomáš: the topology rules and cycle search, `layout`, `toSpec`, `submit`,
`errorRate`, `ExperimentStatus`, `per_second`, `segments`, `toPoints`,
`toxiproxy_config`, `proxy_port`, `service_config`; plans in words first for each.
Decisions by Tomáš: ADR-005, and in ADR-006 the generic service, calling at the same
time, the 30 s retry, grouping by send time, gaps, a line per phase, plain SVG, two
charts, testing the branch now (#80). Found by Tomáš in review: `verdict ?` would have
shown a failed experiment as passed; a GET decision taken without him (#111).

Found on the way: `"kbps": null` stored by the controller vs. the frontend type; the
backend accepts a fault value that does not belong to the kind (#97) and a phase too
short for one request (#98); one slow run of an integration test (#110). Follow-up idea
by Tomáš: time left in the running phase (#99).

Claude's mistakes:

- switched branches in Tomáš's working copy, and once left a branch locked by a worktree,
- said a `git pull` would merge cleanly (add/add conflict in `api.ts`),
- pushed a commit before `make check` had passed formatting (fixed in the next commit),
- decided GET between services without asking (caught by Tomáš in review),
- handed over too much new syntax at once several times (JSX, `segments`, `service_config`).

## Retrospective

**What helped most:** writing TypeScript together, step by step.

**What was hardest:** "the last long function" (the long, many-part functions at the end
of the sprint).

**Self-rated understanding of Sprint 4 code:** 2.5/5 (Sprint 3: 3/5).

**Interview check:** quiz 10/10; own words 4 questions, 3 right on the first try. Weak
spot again the controller crash, now deeper: the record says `inject` until reconcile
runs at the restart (stale state), while the watchdog already removed the fault. Details
in `docs/LEARNING.md`.

## Actions for Sprint 5

1. **Teach-back before planning** of the Claude-written parts: `useExperiment`, the
   generic service, `compose_config`. Tomáš explains, Claude fills gaps.
2. **One new piece of syntax per message.** A long function goes in steps of one block,
   each checked before the next.
3. **Claude never touches Tomáš's working copy**: own worktree on a helper branch, every
   time.
4. Decisions found while coding go to Tomáš before the code, not into the PR afterwards.
