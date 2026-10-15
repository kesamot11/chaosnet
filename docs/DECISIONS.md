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
