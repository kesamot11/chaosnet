# Architecture Decision Records

Significant architectural decisions, newest last. Each record states the context,
the options considered, the decision, and its consequences. Records are never
edited after acceptance except to change their status; a changed decision gets a
new record that supersedes the old one.

---

## ADR-001: Control plane as a modular monolith with lease-based fault cleanup

- **Status:** Accepted
- **Date:** 2026-10-13
- **Issue:** #1

### Context

ChaosNet needs a control plane: the component that starts lab services, injects
and removes faults, drives an experiment through its phases, and collects
results. The data plane is the lab itself: the demo services, Toxiproxy, and the
load generator, through which real requests flow.

The MVP runs on a single developer machine (macOS, Docker Desktop) for a single
user. The most dangerous failure mode of a chaos tool is a fault that outlives
the experiment that created it: the lab stays degraded and every later
measurement is wrong. Toxiproxy keeps toxics in memory indefinitely and has no
notion of experiments or expiry.

### Problem

How should the control plane be structured, and how do we guarantee that faults
are removed even when the control plane crashes?

### Options considered

1. **Modular monolith.** One FastAPI process with internal modules (topology,
   experiments, execution, faults, measurements); experiments run as asyncio
   tasks. Simple to build, debug and explain. A crash orphans active faults.
2. **Control plane + separate executor agent.** API and executor in separate
   processes communicating over HTTP or a queue. Isolates privileged operations
   and fits a future Linux-VM backend, but introduces a distributed system
   (protocol, versioning, partial failure) with no benefit for the MVP.
3. **Declarative reconciler.** Persist desired state; a loop continuously
   converges actual infrastructure to it. Cleanup after restart falls out of the
   design, but experiment phases are awkward to express purely as state and
   eventual consistency is harder to debug.

### Decision

Option 1, borrowing reconciliation from option 3 for faults only, plus an
external dead man's switch. Fault cleanup has three layers:

1. **Normal path:** the experiment runner removes its faults when a phase ends,
   including on cancellation and errors.
2. **Control plane restart:** every fault is persisted *before* it is applied,
   with an owning experiment and an `expires_at` deadline. A reconcile pass on
   startup and periodically removes any fault that has expired or is not
   recorded as owned by a live experiment.
3. **Control plane gone:** a small watchdog running next to Toxiproxy expects a
   heartbeat (lease renewal) from the control plane. If the lease is not renewed
   within a timeout, it resets all toxics.

### Rationale

- The monolith is the simplest structure that meets MVP needs and is easy to
  reason about end to end.
- Layer 2 alone is insufficient: the reconciler runs inside the control plane, so
  it cannot clean up while the control plane is down. Cleanup must not depend on
  the component whose failure it is meant to cover; layer 3 addresses this.
- The watchdog is deliberately tiny, so it is far less likely to fail together
  with the control plane.

### Consequences

- The `execution` and `faults` modules keep narrow interfaces so they can later
  be moved into a separate executor (option 2) when the Network Lab needs a
  privileged agent inside a Linux VM.
- Faults that the watchdog removes leave the experiment record in an inconsistent
  state; the reconciler must mark such experiments as aborted on restart.
- Not covered: if Docker or its VM dies, the watchdog dies too, but so do the
  in-memory toxics, so the lab still ends up clean.
- Assumes a single user on a local machine. Hosting experiment execution for
  other users is out of scope and requires its own security design.

---

## ADR-002: Local-first execution, public demo replays recorded experiments

- **Status:** Accepted
- **Date:** 2026-10-13

### Context

The intended product is a web application where users compose an architecture
in a visual editor and run real experiments against it. Running experiments
means starting containers and holding access to the Docker socket, which is
root-equivalent on the host. Containers share the host kernel.

### Problem

Where does experiment execution run: on the user's machine, or on a server we
host for anyone on the internet?

### Options considered

1. **Local-first.** The user clones the repository and runs the whole
   application (UI, control plane, lab) on their own machine against
   `localhost`. Safe and free, and measurements are real; requires Docker.
2. **Publicly hosted execution.** Every user gets an isolated sandbox (for
   example a Firecracker or gVisor microVM), with authentication, quotas and
   abuse protection. Lowest friction for visitors, but this is a project of its
   own in security and cost, and noisy neighbours distort measurements.
3. **Hybrid.** Option 1 for running experiments, plus a public, read-only demo
   that replays recorded results of real experiments (topology, metrics,
   traces), clearly labelled as recordings.

### Decision

Option 3 as the target. Until the replay demo exists, ChaosNet is local-only.

### Rationale

- No untrusted user ever gets a path to the Docker socket.
- Visitors (for example reviewers of the project) can still see real results
  without installing anything.
- The principle "measure real behaviour, never fabricate" holds: replays are
  recordings of real runs, never synthesised data.

### Consequences

- The control plane binds to `127.0.0.1` only and has no authentication in the
  MVP. This is acceptable only because of this decision.
- Experiment results need a self-contained, exportable format so they can be
  replayed by a static site. This is planned for around v0.2.
- Option 2 remains possible later: ADR-001 keeps execution separable into an
  agent that could run inside a per-user sandbox. It would need its own ADR and
  security design.

---

## ADR-003: Fault injection wiring, cleanup scope and retry safety

- **Status:** Accepted
- **Date:** 2026-10-15 (decided in Sprint 2 planning on 2026-10-13 and during Sprint 2)
- **Issues:** #30–#34
- **Decided by:** Tomáš; reasons below are his, recorded from the discussion

### Context

ADR-001 defined three cleanup layers but not how faults reach the lab, which layers
to build first, or how the watchdog learns that the control plane is alive. Adding a
proxy between services also changed which errors callers see, which made retries
unsafe for some requests.

### Decisions

**1. One Toxiproxy with one proxy per link** (instead of one Toxiproxy per link).
Each proxy has its own toxics, so links stay independently configurable either way.
The only difference is the blast radius of a Toxiproxy crash; one instance means one
API and one `/reset` for the watchdog.
*Reason:* "B has unnecessary overhead that only helps in the rare case that Toxiproxy
crashes." A restart re-creates the proxies from `toxiproxy.json`, and the healthcheck
verifies they were loaded.

**2. Cleanup layers 1 and 3 now, layer 2 (reconcile with a database) in M3.**
*Reason:* a database needs a data model, and the data model belongs to the experiment
controller (M3). Building it now would mean designing it blind and likely redoing it.
Layers are additive: the fault driver and the watchdog are reused unchanged in M3.

**3. Heartbeats are pushed by the control plane: `POST /heartbeat`, empty body, `204`.
The lease timeout is configured in the watchdog, not sent by the client.**
*Reason:* "The first heartbeat might never arrive." The watchdog needs its own timeout
anyway (for startup, before any heartbeat), and one place for the value avoids two
senders (CLI now, controller later) sending different numbers. Push keeps the CLI a
plain client; only the small watchdog is a server.

**4. Heartbeat every 1 s, lease 5 s.**
*Reason:* 1 request per second costs nothing; 5 s tolerates 4 missed heartbeats. The
worst normal stall measured on the Mac (EXP-001, ~40 ms) is 100× shorter. A fault
outlives a crashed owner by at most ~5 s (measured: 4.9 s after `kill -9`).

**5. The watchdog uses asyncio, not threads.**
*Reason:* the watchdog only waits (for heartbeats, for the next check). One thread with
tasks taking turns at `await` needs no locks on the shared lease. Same model as the
load generator and the CLI.

**6. A request that may already have been sent is retried only if it is a GET.**
`ConnectError` and `ConnectTimeout` (never sent) are always retried; `ReadError`,
`RemoteProtocolError` and read timeouts (maybe processed) only for GET. With a proxy in
the path, a stopped service shows up as a cut connection *after* the request was sent.
*Reason:* "You could pay more than 1000 CZK." Repeating a non-idempotent request such
as a POST can apply it twice, and the client cannot tell where the connection broke.

### Alternatives rejected

| Decision | Rejected | Why |
|---|---|---|
| 1 | Toxiproxy per link | N containers and N resets for no gain on one machine |
| 1 | `tc netem` | shapes a whole interface, not one link (netem would also slow gateway↔orders) |
| 2 | all three layers now | database designed before its data model exists |
| 3 | client sends the lease length | watchdog needs a default anyway; two sources of truth |
| 3 | watchdog polls the control plane | the CLI would have to be a server; calling the Mac from a container |
| 5 | threads | locks around shared state, harder to test |
| 6 | retry every transport error | duplicates non-idempotent requests |

### Consequences

- Toxiproxy is a single point of failure for all links. Acceptable for a local lab.
- A fault added directly through the Toxiproxy API, without a heartbeating owner, is
  removed by the watchdog after at most one lease. Faults must have an owner.
- Without layer 2, a fault survives a control plane crash for up to one lease, not
  longer. A crash of the watchdog *and* the control plane together is not covered.
- Non-GET requests fail fast (503/504) instead of being retried after a cut connection,
  so a POST can fail where a retry might have succeeded. Correctness over availability.

---

## ADR-004: Experiment controller: records, storage, concurrency and API

- **Status:** Accepted
- **Date:** 2026-10-18 (decided in Sprint 3 planning on 2026-10-16/17 and during Sprint 3)
- **Issues:** #50–#56
- **Decided by:** Tomáš; reasons below are his, recorded from the discussion
- **Amends:** ADR-001, layer 2 (see decision 8)

### Context

Before Sprint 3 an experiment took three terminals: the fault CLI, the load generator and
a notebook for the numbers. The controller (M3) turns that into one request: it runs the
phases, keeps the results and cleans up. It has to survive its own crash without lying
about what happened.

### Decisions

**1. An interrupted experiment becomes `aborted` with a reason; it is never deleted.**
`aborted` (someone or something stopped it) is separate from `failed` (something broke,
such as a fault that cannot be added).
*Reason:* Tomáš first proposed deleting it, then asked whether a record left in `inject`
does not already say "unfinished". It does not: `inject` means "running right now", so a
dead experiment would look alive forever and block the lab (decision 3). Deleting would
lose the evidence that a crash happened and the phases that were measured.

**2. SQLite through the standard library `sqlite3`; no ORM.**
*Reason:* the database is one file and needs no server to install or run. One user on
one machine needs nothing more.

**3. Only one experiment runs at a time; a second `POST` gets `409`.**
*Reason:* there is only one lab. Two faults at once would mix: with +300 ms on
gateway→orders added during EXP-002, its numbers would show the sum of both faults.

**4. The controller is an HTTP API (FastAPI, async handlers), not a command.**
*Reason:* the UI in M4 needs an API anyway, a long-lived server can send heartbeats, and it
matches ADR-001 (one FastAPI process, experiments as asyncio tasks). Async handlers keep
all database access on the event loop thread, so one SQLite connection needs no locks.

**5. One request describes the whole experiment, including a hypothesis.**
`{name, fault{kind, link, direction, ms|kbps}, load{rate, body}, phases_s{baseline,
inject, recover}, hypothesis{max_p95_ms, max_error_rate}}`. The result has a verdict: did
the inject phase stay within the hypothesis, and if not, why.
*Reason:* Tomáš's fields were "metadata about the fault" and "expected results"; the
expected results became the hypothesis. The healthy state is measured (the baseline
phase), never sent, so it cannot be wrong.

**6. Three separate load runs; the fault window equals the inject measurement window.**
The fault is added right before the inject run and removed right after it, in `finally`.
*Reason:* the inject numbers then contain only behaviour under the fault. Tomáš proposed
one continuous load sliced by time, which would also show the transitions; deferred to
#62, because it needs latency stored over time (M4).

**7. The load target is fixed by configuration, never taken from a request.**
*Reason:* with a target in the request, anything that can reach the API (another program
on the machine, possibly a web page) could aim the load generator at any host (DoS) or at
the local network (SSRF). Whoever can set the controller's environment already controls
the machine.

**8. Reconcile on startup resets all toxics and aborts every running experiment.**
It uses `remove_all` (the same `/reset` as the watchdog), not only `chaosnet-` toxics. If
Toxiproxy is down, the records are fixed anyway.
*Reason:* simpler, and today nothing else creates toxics in the lab. A stopped Toxiproxy
holds no toxics (they live in its memory), so it must not block the records.
*This amends ADR-001 layer 2*, which planned to persist every fault with an owner and an
`expires_at` and to reconcile periodically. With one experiment at a time (decision 3),
every toxic at startup is an orphan, so owners are not needed. While the controller runs,
the runner's `finally` (layer 1) and the watchdog (layer 3) cover it.

### Alternatives rejected

| Decision | Rejected | Why |
|---|---|---|
| 1 | delete the record | loses the evidence and the phases already measured |
| 1 | leave it in its phase | a dead experiment looks alive and blocks the lab |
| 2 | PostgreSQL | a server to run for one user and one file of data |
| 3 | several at once | faults mix and the measurements become meaningless |
| 4 | `chaosnet-experiment run spec.json` | the UI would need an API later anyway |
| 6 | one continuous load sliced by time | needs latency over time; deferred to #62 |
| 7 | `target` in the request | turns the tool into a DoS/SSRF tool for anyone who reaches it |
| 8 | remove only `chaosnet-` toxics | a loop instead of one call, for a case that does not occur today |
| 8 | per-fault records with `expires_at` | not needed with one experiment at a time |

### Consequences

- A record is never in a running state unless an experiment is actually running, after
  any crash (verified: `kill -9` during inject, then restart, gives `aborted`,
  "controller restarted during inject"; integration test in #56).
- Reconcile also removes toxics added by hand, for example with `toxiproxy-cli` while
  debugging. Revisit if another tool ever shares the lab.
- Stopping the server (Ctrl+C) is recorded as "aborted by user" as well.
- An unknown link is found only when inject starts, after the baseline was measured.
- The API has no authentication; that is acceptable only on `127.0.0.1` (ADR-002).

---

## ADR-005: UI stack and a lab generated from a topology spec

- **Status:** Accepted
- **Date:** 2026-10-19 (Sprint 4 planning)
- **Issues:** #71–#80, #62
- **Decided by:** Tomáš; reasons below are his, recorded from the discussion

### Context

M4 adds the first UI: see the lab as a graph, pick a link, run an experiment, watch the
results. The lab is to become customizable, so its shape can no longer live in a
hand-written `compose.yaml` alone.

### Decisions

**1. Vite + React + TypeScript (a single-page app), not Next.js.**
*Reason:* "Next is unnecessary for a local application that needs no SEO." The backend
already exists (FastAPI); Next would add a second server with nothing to do.
The UI reaches the API through the **Vite dev proxy**, so the API sends no CORS headers
and stays closed to other web pages (the threat model behind ADR-004 decision 7).

**2. One `topology.json` describes the lab, and the lab is generated from it.**
A command writes `compose.yaml` and `toxiproxy.json`; `docker compose up` stays a step the
user runs. The controller never gets the Docker socket, which is root on the host
(ADR-002).
*Reason:* the lab will be customizable. A shape hard-coded in the UI would be a third copy
next to compose and Toxiproxy, and they would drift. Tomáš chose generating the lab now
over a read-only spec first ("so the work is not done twice"), in a minimal form: chains
and simple branching, no editor. Format (#72): `version`, services as objects (the entry has
a `port`), links as objects with `from`, `to` and the per-call `timeout_s` and
`max_retries`; one Toxiproxy proxy per link is derived, not written.

**3. The UI polls `GET /experiments/{id}` every second.**
*Reason:* the endpoint already exists and is tested; a result appears once per phase, so
a delay of up to 1 s does not matter. Revisit for the live graph if polling falls short.

**4. React Flow (`@xyflow/react`) draws the topology.**
*Reason:* a customizable lab will need a drag-and-drop editor; React Flow brings panning,
zoom, edge selection and editing. Plain SVG would do today's static picture only.

**5. The latency-over-time graph (#62, #79) is part of Sprint 4.**
Claude recommended Sprint 5 to keep the sprint at ~25 points; Tomáš chose now (31 points).

### Alternatives rejected

| Decision | Rejected | Why |
|---|---|---|
| 1 | Next.js | a second server; SEO and server rendering are not needed locally |
| 1 | CORS on the API | lets any web page the user opens call the controller |
| 2 | nodes hard-coded in the UI | a third copy of the lab's shape; no customization |
| 2 | read-only spec now, generation later | Tomáš: do it once |
| 2 | the controller starts the lab | needs the Docker socket (root) inside a network-facing process |
| 3 | Server-Sent Events, WebSocket | new endpoint and connection handling for no visible gain |
| 4 | plain SVG | the editor would have to be written from scratch |

### Consequences

- New dependency families (npm): versions follow the same 3-day quarantine as Python and
  Actions.
- The committed `compose.yaml` and `toxiproxy.json` become generated files; CI must fail
  when they drift from `topology.json` (#80).
- `TARGET_URL` can be derived from the topology's entry service instead of configured.

---

## ADR-006: One generic lab service, and the decisions made while building M4

- **Status:** Accepted
- **Date:** 2026-10-29 (end of Sprint 4)
- **Issues:** #62, #73, #78, #79, #80
- **Decided by:** Tomáš, except decision 4 (Claude, reviewed and approved by Tomáš in #111)

### Context

ADR-005 decided to generate the lab from `topology.json`. Building it raised questions
the plan had not answered: what runs in a service nobody wrote code for, how a branch
behaves, where settings live, and how the UI shows time.

### Decisions

**1. Every node runs one generic service** (`lab/src/chaosnet_lab/service.py`).
It calls every service it links to and a leaf answers at once. The shop (items, stock,
404 for an unknown item) is gone. *Reason:* the lab exists to measure the network
between services; with code per service, the JSON would need Python next to it.

**2. A service calls its callees at the same time** and waits for all of them, so it
waits for the slowest. *Reason (Tomáš):* faster, and how most services that gather data
from several others behave. Verified end to end in #80.

**3. One failed callee fails the whole request**, naming the hop (`failed_hop`).

**4. Services call each other with GET** (the entry still takes the load generator's
POST). A generic service changes nothing, so a call may be repeated, and
`call_downstream` retries a GET after a timeout. This keeps the orders→inventory budget
(3 × 0.5 s) the integration tests rely on.

**5. Per-link timeouts and retries live only in `topology.json`.** The environment
overrides (`ORDERS_MAX_RETRIES`, ...) are gone. *Reason:* two ways to set one value are
two truths. For the same reason one function, `proxy_port`, gives a link's proxy port to
both halves of the generator.

**6. The UI keeps polling while the controller does not answer**, every 30 s instead of
every second, and back to 1 s once it answers. *Reason (Tomáš):* stopping would show
`inject` forever; after a restart reconcile writes `aborted`, and only a poll can show it.

**7. Latency over time is grouped by the second a request was sent**, a second without
requests is a gap (not left out, not 0), and the graph breaks its line at phase borders.
*Reason (Tomáš):* by answer time a fault would appear seconds late; a line through a gap
or across a border shows values nobody measured.

**8. The graph is plain SVG, two charts on one time axis.** This reverses ADR-005
decision 4 for the graph only (React Flow stays for the topology). *Reason (Tomáš):* one
chart of a few dozen points does not justify a chart library and its dependencies; two
axes in one chart are hard to read.

### Consequences

- Experiments cannot model application behaviour (a slow database, a 404); a service
  type in the topology would be the way back if needed.
- `compose.yaml` is generated as JSON with a YAML comment header (JSON is valid YAML), so
  no YAML library; a test fails when it drifts from `topology.json`.
- A topology service may not be called `toxiproxy` or `watchdog`.

---

## ADR-007: Retry amplification first, measured with Prometheus

- **Status:** Accepted
- **Date:** 2026-10-30 (Sprint 5 planning)
- **Issues:** #115–#122, epic #7 (M6)
- **Decided by:** Tomáš; reasons below are his, recorded from the discussion

### Context

With timeouts and retries on every hop, a slow service can receive many times the
requests its callers received: gateway→orders allows 2 attempts, orders→inventory 3, so
one user request can become 6 at inventory exactly when it is struggling (retry
amplification). To show it, the experiment must count the requests that reach each
service, but only the entry and the control APIs are reachable from the Mac.

### Decisions

**1. M6 (resilience) before M5 (observability).** *Reason:* it builds on what exists
(retries, faults, the controller), needs little new infrastructure, answers the open
question from EXP-002, and completes v0.2.0. M5 follows.

**2. Prometheus counts the requests**, as a container in the generated lab that scrapes
every service's `/metrics` inside the lab network; only Prometheus is published, on
`127.0.0.1`. New infrastructure, approved by Tomáš. *Reason:* the standard tool for
this, so the skill is real, and half of M5 (metrics) is done with it.

**3. Mitigations now: retry on one layer only, and backoff with jitter.** Retry budget
and circuit breaker in Sprint 6, together, as both keep state. *Reason:* Sprint 4's 31
points brought understanding down to 2.5/5; 24 points this time.

**4. Storing the counts with the results (#121, #122) is optional**, decided after
EXP-004. *Reason (Tomáš):* querying Prometheus by hand may be enough.

### Alternatives rejected

| Decision | Rejected | Why |
|---|---|---|
| 2 | an own `/stats` per service | would need the services' ports published or a collector written by hand |
| 2 | counting at the entry only | shows latency, not how many attempts reached inventory |
| 3 | all four mitigations now | too much for one sprint |

---

## ADR-008: A circuit breaker per link, and a retry budget

- **Status:** Accepted
- **Date:** 2026-10-31 (Sprint 6 planning)
- **Issues:** #134–#139, epic #7 (M6)
- **Decided by:** Tomáš; reasons below are his, recorded from the discussion

### Context

EXP-004 and EXP-005: a hanging service gets ×3 to ×6 the requests while it struggles,
every user waits for the timeouts, and retry on one layer or backoff only soften it.
Sprint 6 adds the two mechanisms that keep state: a circuit breaker (stop calling a
service that keeps failing) and a retry budget (cap the share of retries).

### Decisions

**1. The breaker opens at more than 50 % failures in the last 10 s, counted only when
the window holds at least 10 requests.** *Reason (Tomáš):* a count of failures in a row
misses a pattern like "1 good, 2 bad" repeated, which fails 66 %. The minimum stops a
single failure in a quiet window (100 %) from opening the breaker and refusing a whole
morning of healthy traffic: a false alarm is an outage too.

**2. One breaker per link, at the caller**, like the attempt counter (#116).

**3. Open: no call, no retry, an answer at once:** `503 {"error": "circuit_open",
"failed_hop": "orders->inventory"}`. *Reason (Tomáš):* the error names the cause,
unlike retry on one layer, which hid it (EXP-005).

**4. After a 5 s cooldown, half-open: one trial call.** It succeeds: closed; it fails:
open again.

**5. Both off by default** and set per link in `topology.json`, like `backoff_s`.

### Alternatives rejected

| Decision | Rejected | Why |
|---|---|---|
| 1 | N failures in a row | misses alternating failures |
| 1 | a rate without a minimum | one failure at night opens the breaker |
| 3 | waiting for the timeout anyway | the user waits for an answer already known |
