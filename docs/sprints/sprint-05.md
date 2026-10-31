# Sprint 5: review and retrospective

- **Dates:** 2026-10-30 to 2026-10-31
- **Goal:** cause a retry storm in the lab, measure it, and measure the mitigations.
- **Result:** goal met. 19 of 24 points; the other 5 (#121, #122) dropped by Tomáš after
  EXP-004 (YAGNI), as planned in ADR-007.

## Review: what works (demonstrated)

| Issue | Outcome | Evidence |
|---|---|---|
| #115 ADR-007 | M6 before M5, Prometheus approved, mitigations 1 and 2 | `docs/DECISIONS.md` |
| #116 Prometheus | requests per service, attempts per hop and outcome, counted by the caller | unit + integration: one request counted once per service and hop |
| #117, #118 EXP-004 | retry amplification ×3 (today) and ×6 (gateway timeout 1.0 s) | `experiments/exp004.py`; both predictions correct |
| #119 backoff | `backoff_s` per link with full jitter; warning when a link times out before its callee may answer | unit tests with a fake sleep; generator warns on EXP-004 B |
| #120 EXP-005 | retry on one layer ×6 → ×3; backoff halves failures in a 1 s outage at a latency cost | `experiments/exp005.py`; predictions: part 1 exact, backoff 8 vs 11 measured |
| #97, #98 | 422 for a fault value of another kind, and for a phase without a request | unit tests; #98 found three tests with half a request per phase |
| #110 spike | slow 503 measured: only the first run after an image build; DNS ruled out | issue comment |

Written by Tomáš: the metric design (count at the caller, a paused service counts
nothing), `retry_wait`, `answer_time_s`, `amplification_warnings`, the #97 and #98
validators; all predictions. Decisions by Tomáš: M6 before M5, Prometheus, mitigations
1 and 2 now, warning instead of error, dropping #121/#122, all three phases in #98.
Found by Tomáš: that a cure (backoff) can cause the storm it fights; that I had written
"you write it" and then wrote the prediction myself.

Not predicted, found by measuring: abandoned requests are still processed after a
paused service resumes (zombie requests); a shorter outer timeout doubled the load and
made the user wait longer.

Claude's mistakes:

- pushed twice before `make check` was clean (formatting, line length),
- wrote a quiz question that depended on an unstated config,
- said "you write the prediction" and then wrote it,
- created a duplicate issue (#123 for #110),
- old tests with phases of half a request, found by Tomáš's #98 rule.

## Retrospective

**What helped most:** the explanations; the sprint was short and nothing was too hard.

**What was hardest:** how backoff works exactly.

**Self-rated understanding of Sprint 5 code:** 3–4/5 (Sprint 4: 2.5/5).

**Interview check:** quiz 10/10 (one question was faulty and counted as correct); own
words: the stale state after a controller crash is now right (the weak spot of Sprints
3 and 4). Weak spots: jitter vs backoff; the watchdog reacts to an expired lease, it
does not watch the controller; telling EXP-004 B from EXP-005 part 1. Details in
`docs/LEARNING.md`.

## Actions for Sprint 6

1. Keep sprints around 20 points: understanding went from 2.5 to 3–4.
2. Retry budget and circuit breaker (ADR-007): start with a drawing of each, before code.
3. `make check` must be clean before every push, with no exception.
