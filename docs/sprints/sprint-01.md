# Sprint 1: review and retrospective

- **Dates:** 2026-10-13 (planned 2026-10-13 to 2026-10-19; scope finished on day 1)
- **Goal:** reproducible environment with green CI, and a running demo system
  `gateway -> orders -> inventory` with a repeatedly measured healthy baseline.
- **Result:** goal met. 8/8 issues, 20/20 points.

## Review: what works (demonstrated)

| Issue | Outcome | Evidence |
|---|---|---|
| #9 backend skeleton | uv, Python 3.14, ruff, pyright strict, pytest; `make check` | clean-clone run |
| #10 CI | 3 required checks, ruleset on `main`, squash-only | deliberately failing PR #20 was blocked |
| #11 templates | PR template with DoD, issue form | used by later PRs |
| #12 spike | Toxiproxy, netem and host reachability verified on Apple Silicon | `docs/ARCHITECTURE.md` |
| #13 demo system | 503 on stop (~10 ms), 504 on pause (1.52 s), recovery | 7 integration tests in CI |
| #14 load generator | open model; 1515 ms p95 where a closed-loop client showed 11 ms | `docs/LEARNING.md` |
| #15 baseline | healthy p50/p95/p99 4.9/10.5/12.2 ms from the Mac | `docs/EXPERIMENTS.md` EXP-001 |
| #16 architecture | overview, request flow, failure table, diagram | `docs/ARCHITECTURE.md` |

Written by Tomáš (test-first): `call_downstream`, `percentile`. Found in Tomáš's
reviews: unvalidated `DOWNSTREAM_URL` (healthy-but-broken service), missing values
in a validation error.

## Retrospective

**What helped learning:** explanations and predictions before measuring.

**What did not work:**

- TDD tasks were over-scaffolded: the docstring said step by step what to write.
- Reviewing PRs without knowing what to look for.
- Claude wrote hundreds of lines, Tomáš ~20. Self-rated understanding of
  Claude-written code was **1/5** at the end of the sprint.
- Claude's process mistakes: required checks added before older PR branches had
  them (PR #21 stuck), Projects automation broken while editing statuses, two
  unverified or wrong claims in PR text that had to be corrected.

**After a walkthrough of all components:** self-rating 3/5, diagnostic quiz 10/10.
Interpretation: concepts are understood (recognition); producing explanations and
code unprompted (recall) is the gap. That comes from doing, not more reading.

## Actions for Sprint 2

1. Tomáš writes the core logic (fault driver, watchdog); Claude writes boilerplate.
   Lower velocity is expected and accepted.
2. TDD tasks: problem + tests + bare signature only. Hints on request.
3. Each PR gets 2-3 "where to look" pointers for review, not the findings.
4. Explanations visual-first, short, one question at a time.
5. Before changing required checks, update or merge open PRs first.

## Notes for planning

20 points in one day is not a reusable velocity: most of it was one-off setup
(M0), and Sprint 2 deliberately shifts implementation to Tomáš.
