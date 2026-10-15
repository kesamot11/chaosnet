# Sprint 2: review and retrospective

- **Dates:** 2026-10-14 to 2026-10-15 (planned 2026-10-14 to 2026-10-20)
- **Goal:** apply a fault from the terminal, see p95 rise in measurements, and the fault
  always disappears: at the end, on Ctrl+C and on `kill -9`.
- **Result:** goal met. 23/24 points; #37 (Dependabot decisions) moved to 2026-10-16 by
  choice (quarantine). #40 fixed by an external contributor (PR #42).

## Review: what works (demonstrated)

| Issue | Outcome | Evidence |
|---|---|---|
| #30 Toxiproxy in the lab | both links proxied; no measurable overhead | EXP-001b |
| #31 fault driver | latency, bandwidth, reset_peer; idempotent remove | unit tests + real lab |
| #32 fault CLI | cleanup at end, on SIGINT and SIGTERM | integration tests |
| #33 watchdog | fault removed 4.9 s after `kill -9` of its owner | integration tests |
| #34 cleanup tests | "a fault never outlives its owner" checked in CI | 12 integration tests |
| #35 ADR-003 | 6 decisions with their reasons | `docs/DECISIONS.md` |
| #36 EXP-002 | a timeout turns slowness into an outage ("cliff") | `docs/EXPERIMENTS.md` |

Written by Tomáš: most of the fault driver, the watchdog `Lease` and `watch` loop, the
idempotent retry rules in `call_downstream`. Review findings by Tomáš: 7 real issues
(2 in #38, 3 in #43, 2 in #47), one of them not known to Claude beforehand. EXP-002:
3 of 4 predictions correct. First external contribution reviewed and merged (#42),
reading every diff version before approving fork CI.

Claude's mistakes: #31 handed over as one unscaffolded six-method task (too big a step);
first fault CLI ignored SIGINT when started in the background; two edits silently not
applied (caught by tests); a shell comment in a command that broke zsh; wrong flag order
in a demo.

## Retrospective

**What helped:** reading and writing code noticeably improved; the "I do, we do, you
do" pace for new code is "ideal".

**What was hardest:** the six-method fault driver task.

**Self-rated understanding of Sprint 2 code:** 3/5.

## Actions for Sprint 3

1. "I do, we do, you do" is the default for every new module. At most 1–2 methods per
   independent step.
2. Before Sprint 3 planning: teach-back walkthrough of the Claude-written parts (fault
   CLI and signals, watchdog lifespan, integration fixtures, Toxiproxy wiring). Tomáš
   explains, Claude fills gaps.
3. Keep: real review with a checklist, predictions in their own PR before measuring.
