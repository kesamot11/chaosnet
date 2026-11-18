# Sprint 11: review and retrospective

- **Dates:** 2026-11-14 to 2026-11-19
- **Goal:** a public demo a visitor can click through in a minute, without Docker, that
  replays real recorded runs (epic M9, #231; ADR-012).
- **Result:** goal met in the repository. #232–#238 are done. The demo goes public with
  the next release, which deploys it to GitHub Pages (Tomáš's action).

## Review: what works (demonstrated)

| Issue | Outcome | Evidence |
|---|---|---|
| #232 ADR-012 | the demo is the UI built as a static site; it replays recorded runs and generates nothing | PR #239 |
| #233 export | `make demo-export` saves a run as the API's own JSON, plus an index of the runs | PR #240 |
| #234 replay | the demo build reads the files instead of the controller; a run replays 5× faster, each phase's results appear when the phase ends | PR #241 |
| #235 demo UI | click a link, pick a recorded run, Start; no editor, no fault form, no traces | PR #242; run in the browser |
| #236 recordings | three runs of the same experiment on orders → inventory, one setting changed: timeout only, breaker, fallback | PR #243; real runs of the lab |
| #237 Pages | a workflow builds the demo under `/chaosnet/` and deploys it when a release is published | PR #247; Pages settings checked, not yet deployed |
| #238 README | Tomáš's sentence, the demo link, a screenshot, every experiment in one line | PR #249 |

The recorded runs (inject phase, inventory +1000 ms, 0.5 s timeout, no retries, 20 req/s):

| Run | p50 | p95 | Answers | Verdict |
|---|---|---|---|---|
| Timeout only | 513 ms | 521 ms | 300 × 5xx | failed |
| Circuit breaker | 12 ms | 517 ms | 300 × 5xx; 26 more in recover | failed |
| Fallback | 513 ms | 521 ms | 300 × `degraded`, 0 errors | passed |

The fallback run passes although every answer was degraded: the hypothesis checks only
p95 and the error rate, and `degraded` is not an error.

Decided by Tomáš:

- interactive, not a video: the visitor clicks through it alone, and it doesn't go stale
  with the UI,
- a replay plays like a real run (progress, each phase's results at its end, magenta
  during inject, the verdict last), only 5× faster,
- no fault form in the demo: fields that change nothing would look fake,
- runs picked per link, with a name and one sentence each; Start waits while a replay
  runs, and says why,
- the same run can be replayed again,
- three runs that differ in one setting only (a controlled experiment),
- the demo deploys at each release, not at each push to `main`: the web shows the
  released version,
- the README lists every experiment instead of one chosen number, and says that the
  demo's numbers come from its own runs,
- #248 (the lab hidden under the Latency drawer after Start) is changed only if it turns
  out better.

Found by running by hand:

- the README screenshot showed that the Latency drawer covers the lab after Start, in
  the demo and in the real UI (#248).

Claude's mistakes:

- PR #243 was pushed before `make check`; it ran after the push (green),
- a long local setup was offered for a simple review question on PR #242.

## Retrospective

**What helped:** nothing in particular.

**Self-rated understanding:** what was built 4/5; the code 2/5 (Sprint 10: 3/5).

**Interview check:**

- Quiz: 9/10 (Sprint 10: 6/10). Missed: a phase's results appear when the phase ends,
  as in a real run (not second by second). Question 9 was a typo and is counted right.
- Own words:
  - **How the demo works without a backend, and why:** right on why (no public API,
    not a video, the visitor's own pace). Said the demo "simulates" the runs; it replays
    real recorded runs unchanged, only faster. Missing: the write code is not in the
    demo build.
  - **Is a fallback better than a breaker?** The breaker right. The fallback after a
    fill-in sentence: it answers without the failing service, it does not explain the
    error, and it still calls inventory every time. Together they complement each other
    (EXP-010).
  - **Why the svg is `absolute` (Sprint 10 revisit):** still a weak spot; right only
    after a fill-in sentence. **Revisit in the Sprint 12 check.**

## Actions for Sprint 12

1. Keep the open design question first; Claude says CSS and browser mechanisms in one
   line before coding them.
2. Understanding of the code fell to 2/5: in each PR, Claude shows the few lines that
   matter and asks one question about them.
3. Candidates: release v0.6.0 (Tomáš, with a full SHA), which puts the demo online;
   close epic M9 (#231); try #248.
