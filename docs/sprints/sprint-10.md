# Sprint 10: review and retrospective

- **Dates:** 2026-11-07 to 2026-11-14
- **Goal:** a polished UI that looks like a current web app, not the browser's defaults
  (epic M8, #205).
- **Result:** goal met. #206–#211 are done, and so is #200 (tests no longer read the real lab).
  Plain CSS with variables, no new dependency, and the "AI design slop" list was kept.

## Review: what works (demonstrated)

| Issue | Outcome | Evidence |
|---|---|---|
| #200 tests | backend tests use their own topology, not `lab/` | PR #212 |
| #206 theme | a dark theme in plain CSS; magenta only for an active fault | PR #213; run in the browser |
| #207 layout | the lab fills the screen; drawers slide over it; the bottom panel can be resized | PR #214; run in the browser |
| #208 editor | the editor sits in the left drawer; unsaved changes and Save are in the top bar | PR #215; run in the browser |
| #209 experiment | the experiment sits above its form; tables have a grid; Start waits during a run and says why | PR #216; a real experiment in the lab |
| #210 chart | charts are stacked and grow with the panel; text and dots keep their size | PR #217; a real 35 s experiment, panel 421 → 621 px |
| #211 links | a link that would cross a service arcs over it, also while dragging | PR #228; a draft in the browser (Docker was off) |

Decided by Tomáš:

- the dark-grey palette (after thompsondj.com): violet for selection and the main
  action, magenta only while a fault is active,
- plain CSS with variables, no UI library,
- drawers cover the lab instead of narrowing it; all are closed at start; hovering
  enlarges a handle; handles have a violet tint,
- the bottom panel is resized by dragging its top edge,
- "Unsaved changes" and Save in the top bar, doing the same as the editor's Save; a
  refused save opens the editor,
- link settings inside the editor; one field per line,
- the experiment above its form; Start disabled while one runs, with the reason; a
  wider right drawer; tables with headings, units in headers and a full grid,
- charts stacked; they grow with the panel ("taky se zvětšit, zmenšit"),
- a link avoids services with a collision detector and bends around them, as an arc.

Found by Tomáš:

- in review of #214: a dragged height pushed the panel's edge off screen when the
  window shrank (fixed with `max-height`),
- in review of #215: the experiment form's fields were not on one line each,
- in #216: the first tables were cramped and unclear.

Found by running by hand:

- #228: a service lying on an end of a link sent the arc off screen; the first arc rose
  too slowly and also flew off.

Claude's mistakes:

- a vague first design question in #209 ("what should it show?"),
- the first styling for #208 missed the experiment form,
- #211 was not tried in the running lab with a hand-drawn link (Docker was off),
- quiz question 10 could be read two ways.

## Retrospective

**What helped:** Tomáš designs in words, and Claude writes the code and shows it.
"I liked how I thought it through and wrote a bit of code." A little code now and then
helps, but not much is needed.

**What was hardest:** nothing in particular.

**Self-rated understanding of Sprint 10 code:** 3/5 (Sprint 9: 3/5).

**Interview check:**

- Quiz: 6/10 (Sprint 9: 5/7). Three of the four misses are about *why* CSS behaves as it
  does:
  - `max-height` keeps a dragged panel on screen; `height: 50%` holds only until the
    first drag,
  - magenta means only an active fault (inject); a selected link is violet,
  - the svg is `absolute` so its size can't change what is measured (feedback loop),
  - a *foreign* service on a link's end is ignored because no arc can go around it.
- Own words:
  - **How links avoid services:** right in outline (32 pieces, check, move). Missing:
    the arc rises 20 px and the check runs again (a loop, at most 30 times), the
    12 px margin, and that it happens during the drag.
  - **Why the chart measures its place:** right on why (text and dots would scale).
    Didn't know the feedback loop; learned it here. **Weak spot.**
  - **Why Toxiproxy and Prometheus restart (Sprint 9 revisit):** right after a
    fill-in sentence: they read their config only once, at start.
  - **Save answers at once (Sprint 9 revisit):** right: a refresh would lose a result
    that lives in one HTTP request. Fixed since Sprint 9.

## Actions for Sprint 11

1. Keep the open design question first; show a little code now and then.
2. When a decision rests on how CSS or the browser behaves, Claude says the mechanism in
   one line before coding it (the quiz showed this is the gap).
3. Run every UI change in the running lab, not only on a draft.
4. Candidates: close epic M8 (#205) and release v0.5.0; then the public replay demo
   (ADR-002).
