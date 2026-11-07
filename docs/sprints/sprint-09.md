# Sprint 9: review and retrospective

- **Dates:** 2026-11-06 to 2026-11-07
- **Goal:** a drag-and-drop topology editor: the lab is drawn and configured in the UI and
  applied with one click (epic M7, #188).
- **Result:** goal met. 24/24 points (22 planned; #185 grew from 3 to 5 when experiments
  started to record their topology).

## Review: what works (demonstrated)

| Issue | Outcome | Evidence |
|---|---|---|
| #189 ADR-011 | Save applies the topology: the controller runs a fixed `docker compose` command | `docs/DECISIONS.md` |
| #190 PUT /topology | a topology is checked (shape and rules) and saved atomically; a broken one gets 422 | API tests |
| #191 apply | regenerate, restart, wait; a failed start rolls back, a failed rollback is `failed` with both errors; `GET /lab` | API and lab tests; `make integration` |
| #192 move | services are dragged; positions are saved without restarting the lab, also during an experiment | PR #198; run by hand in the lab |
| #193 services | add and remove services in a draft; Save applies it; one selection at a time | PR #199; run by hand in the lab |
| #194 links | draw a link from caller to callee; a duplicate or a link to itself is not added and says why; remove a link | PR #201; run by hand in the lab |
| #185 settings | timeout, retries, backoff, budget, breaker and fallback per link; every experiment records the topology it ran on | PR #202; run by hand on the real lab and database |

Decided by Tomáš:

- Save applies the topology (no separate "apply" button); no limit on the number of
  services, the lab is local,
- refusals: while an experiment runs, while the lab restarts; Start only while the lab
  runs,
- a failed start rolls back, with what went wrong; a failed rollback is `failed`,
- the controller applies `topology.json` at startup,
- a positions-only save doesn't touch the lab and is allowed during an experiment,
- lab changes wait in a draft until Save; a move during a draft goes into the draft,
- a new service gets the entry port only in an empty lab,
- names are checked by the controller only (one copy of the rule),
- one selection at a time, never of something that is gone,
- a new link gets the controller's defaults; a duplicate or a link to itself is refused
  in the editor with why, a cycle by the controller on Save,
- any link can be selected; a link without a proxy says why there is no fault form,
  differently for an unsaved and a saved one,
- Start with unsaved settings stays allowed, with a warning,
- experiments record the whole topology; the result shows every link; old ones say
  their settings were not recorded,
- an empty retry budget means no budget,
- refusals name the link or service, not its place in the list,
- the words of the lab line ("The lab is restarting, hold on a moment…" and the others).

Found by Tomáš:

- in review of #193: a link and a service could be selected at once; a single link could
  not be removed,
- in the #192 manual run: a lab saved without links broke 18 backend tests, which read
  the real `lab/topology.json` (#200).

Found by running by hand:

- a saved link without a proxy advised "Save the lab", and Save was disabled (#194),
- a refusal named "links.1" instead of the link (#185),
- the experiment database from before #185 opened and kept its 9 experiments.

Claude's mistakes:

- skipped `make integration` before #197; CI went red (409 while the lab restarted),
- skeletons with lines over the length limit,
- opened the browser pane when asked *how* to open it,
- wrote "#185" without saying what it was,
- decided the system design of #193–#185 alone and asked only about UI behaviour,
- quiz question 8 offered no exactly right answer (voided).

## Retrospective

**What helped least:** Claude did too much of the implementation and left no system
design to Tomáš. Coding needn't be his, thinking should be.

**What was hardest:** nothing in particular.

**Self-rated understanding of Sprint 9 code:** 3/5 (Sprint 8: 3.5–4), as Claude wrote
most of it.

**Interview check:**

- Quiz: 5/7, question 8 voided (Sprint 8: 7/8).
  - Missed: why Save restarts Toxiproxy and Prometheus too (they read their config only
    at start).
  - Missed: why `ALTER TABLE` is needed although the schema has the column
    (`IF NOT EXISTS` skips the whole statement for an existing table).
- Own words:
  - **From Save to "running":** right on the atomic write, the restart and the result;
    missing the checks first (422, 409), the immediate answer, `write_lab` and the poll
    of `GET /lab`.
  - **Why Save answers at once:** first thought of a stale topology after a refresh;
    the real loss is the restart's *result*, which would live in one HTTP request.
    Refined: async request-reply, the state lives on the server.
  - **A failed topology and a failed rollback:** right, in the user's words.
  - **Why Toxiproxy restarts:** right after the quiz explanation; refined: no proxy
    means connection refused, and the caller reads its calls only at start too.
  - **Why every experiment stores its topology:** right; refined: a snapshot, so an old
    record stays true.

## Actions for Sprint 10

1. Per task, an **open system-design question first**, without options; Tomáš proposes,
   Claude reviews, then Claude codes. A/B/C only for details.
2. Keep the manual run in the lab before every PR, and `make integration` when the
   controller's startup, its refusals or the lab change.
3. Candidates: a polished UI (Sprint 10 goal); #200 (tests must not read the real lab);
   close epic M7 (#188) and release v0.4.0.
