# Learning log

Concepts encountered while building ChaosNet, in the order we met them.
Includes the questions I got wrong or only partly right, because those are the
ones worth revisiting.

---

## 2026-10-13: Control plane, reconcile, and fault cleanup

### Control plane vs. data plane

Terms borrowed from networking. In a router, the **data plane** forwards packets
using a forwarding table; the **control plane** (OSPF, BGP) decides what goes
into that table.

In ChaosNet the data plane is the lab: the demo services, Toxiproxy and the load
generator, through which real requests flow. The control plane is our backend:
it never carries requests, it decides what runs and which faults are active.

Key consequence: when the control plane dies, the data plane keeps running,
including any fault that was active at that moment.

### Imperative vs. declarative control, and reconciliation

- **Imperative:** "add toxic", later "remove toxic". The intent to remove lives
  only in the memory of the running process.
- **Declarative:** persist the desired state ("fault F1 may exist until 14:05,
  owned by experiment E7"). A **reconcile loop** repeatedly compares actual state
  (ask Toxiproxy) with desired state (database) and removes the difference. It
  needs no memory of the past, so it works after a restart.

### TTL and the dead man's switch

A fault has a deadline (`expires_at`, a TTL). But a deadline does nothing unless
some running component enforces it.

**Question:** the control plane crashes at 14:02 while a fault is active and is
never restarted. What happens?

- *My answer, part 1:* the lab stays degraded forever. **Correct.**
- *My answer, part 2:* give the fault a time limit so it resets at 14:10.
  **Partly correct.** The TTL idea is right, but I missed *who* performs the
  reset. The reconciler runs inside the dead control plane, so nobody does.

**Principle:** cleanup must not depend on the component whose failure it is
meant to cover.

**Fix:** a dead man's switch, also called a lease. The control plane sends a
heartbeat every few seconds; a separate tiny watchdog resets all faults if the
heartbeat stops. The safe state is triggered by the *absence* of a signal.
Kubernetes and etcd use leases the same way. See ADR-001.

---

## 2026-10-13: Container networking is real networking

**Question:** why is only the gateway port published to the host?

- *My answer:* because everything runs locally, so traffic does not go through
  the network layer. **Incorrect.**

Containers talk over a real TCP/IP stack. Each container has its own network
namespace (interfaces, IP, routing table, ARP table), connected by veth pairs to
a Linux bridge inside the Docker VM. Even `localhost` goes through the loopback
interface. "Local" only means the packets never leave one kernel, so the network
is idealised (no physical loss, near-zero latency). That is why we degrade it
artificially.

Actual reasons for publishing only the gateway:

1. Experiments must not be bypassable. Every request must take the path where
   faults are injected, or measurements are wrong.
2. It mirrors production: internal services sit behind a single entry point,
   which keeps the attack surface small.
3. Services find each other by name through Docker DNS (`http://inventory:8000`),
   which is real service discovery.

---

## 2026-10-13: Latency is one-way; RTT is the sum of both directions

From spike #12: netem `delay 100ms` on the pinging container's `eth0` gave a ping
RTT of ~103 ms, not 200 ms. A Toxiproxy latency of 300 ms on one stream gave
~0.30 s, and on both streams ~0.61 s.

**Questions:** why not 200 ms? Why does the delay double with both streams?

- *My answer 1:* because netem is RTT. **Incorrect, it is the opposite.**
- *My answer 2:* because it gets divided. **Incorrect, the delays add up.**

netem shapes **egress** only: packets *leaving* the interface it is attached to.
The echo request left the pinging container and was delayed by 100 ms; the echo
reply left the *other* container and was not delayed. RTT = 100 + ~0.2 ms.

Toxiproxy works the same way: `upstream` delays client-to-server bytes,
`downstream` delays server-to-client bytes. A request/response needs both
directions, so the delays add: 300 + 300 = 600 ms.

**Rule:** RTT = one-way delay there + one-way delay back. Every fault definition
in ChaosNet must state whether a latency is one-way or round-trip.

---

## 2026-10-13: Netem works per interface, not per link

**Question:** how do you add exactly 200 ms of RTT to `orders -> inventory`?

- *My answer:* Toxiproxy 100 ms; netem 200 ms on one side or 100 ms on both.
  **Mostly right.** For Toxiproxy it must be 100 ms on *both* streams (or 200 ms on
  one), and the direction has to be stated explicitly.

The trap I did not see: netem attaches to an **interface**. `orders` has one `eth0`,
which carries traffic to inventory *and* responses to the gateway. Netem on it
slows down `gateway <-> orders` too, so the experiment would measure something
other than what it claims. Toxiproxy works per proxy, which means per link.
Targeting one link with netem needs `tc` filters by destination or a separate
Docker network per link. That is why the MVP uses Toxiproxy and netem comes later.

---

## 2026-10-13: Name resolution comes before ARP

**Question:** `docker stop inventory`, then `orders` calls `http://inventory:8000`.
What error does `orders` get?

- *My answer:* 503 because it is down, not a timeout; the IP is found via ARP.
  **Status code right, mechanism wrong.**

Order of lookups: **DNS** (name to IP, Docker's embedded server at `127.0.0.11`),
then **ARP** (IP to MAC on the bridge), then the TCP handshake. A stopped container
is removed from Docker DNS, so resolution itself fails:
`Name or service not known` (measured, see ARCHITECTURE.md). "Connection refused"
would only happen if the container were running but nothing listened on the port
(the kernel answers the SYN with RST).

---

## 2026-10-13: Writing `call_downstream` (my first function in ChaosNet)

Written test-first: the tests existed and failed before the implementation.

Mistakes I made and what they taught me:

1. **`raise` inside the retry loop.** `raise` ends the whole function, just like
   `return`, so only one attempt ever happened. Inside the loop you do not yet
   know whether a failure is final; remember it, and decide after the loop.
2. **`return null`.** Python has `None`; `null` is Java/JS. And after the loop
   there should be no return at all, only `raise`.
3. **"possibly unbound".** If the loop runs zero times (`max_retries = -1`),
   `code` never gets a value. `code = None` only moved the problem (a status of
   `None` makes no sense). Fix: **fail fast** on invalid input
   (`max_retries < 0` raises `ValueError`) plus a typed initial value, because the
   type checker cannot prove that `range(n)` runs at least once.
4. **Error message must match the condition:** `0` retries is valid, so the
   message says `>= 0`, not "larger than 0". Use an f-string, not two arguments
   to `ValueError`.

Takeaway: tests passed after step 1, but pyright still found a real bug. Each
quality gate catches a different class of problem.

---

## 2026-10-13: Coordinated omission

**Question:** a service normally answers in 5 ms and freezes for 2 s during a 10 s
test. One worker sends, waits for the answer, then sends again (target 10 req/s).
How many requests, how many slow, and what p95 does the tool report? How many
real users (arriving every 100 ms independently) would see a slow response?

- *My answers:* ~80 requests, 1 slow, p95 close to 5 ms, 20 % of real users.
  **All correct.**

That is **coordinated omission**: a closed-loop client coordinates with the system
under test. It stops sending exactly while the system is slow, so the worst samples
are never taken. Real users do not wait for each other.

Fix (open model): schedule request *i* at `start + i / rate` regardless of
responses, send each as an independent task, and measure latency from the
**scheduled** time, so a late generator cannot hide delay either. Track send lag to
detect a saturated generator. Never wait for a free slot; record it as dropped.

Measured on the real lab (20 req/s for 10 s, `docker pause inventory` for 2 s
starting at 4 s):

| | requests sent | errors | p95 |
|---|---|---|---|
| Naive closed-loop client | 152 of 200 | 1 | **11.4 ms** |
| `chaosnet.loadgen` (open model) | 200 of 200 | 12 | **1514.6 ms** (all), 1079.5 ms (ok) |

The same freeze was reported as ~130x better by the naive client.

---

## 2026-10-13: Writing `percentile` (nearest rank)

Mistakes I made:

1. **Missing `import math`.** All tests failed with the same `NameError`, which hid
   every other bug. Read the `E` lines of the test output; fix the first error,
   rerun, read the next one.
2. **Rank vs. index.** Ranks are 1-based, list indices are 0-based, so index =
   rank - 1. Without it, p100 raises `IndexError` and everything else is off by one.
3. **Float rounding.** `14 / 100 * 100` is `14.000000000000002`, and `ceil` turns it
   into 15. In my words: multiply first, because then you multiply whole numbers.
   More precisely, products of integers are exact in a float (up to 2^53), so only
   the final division rounds, once; dividing first creates an inexact intermediate
   that the multiplication then amplifies. I first wanted an epsilon tolerance; it
   would work, but the threshold is a magic number and it hides the cause instead of
   removing it.

---

## 2026-10-13: Proxies, cut connections and idempotent retries

Adding Toxiproxy between services changed how "inventory is stopped" looks to
`orders`: it now connects successfully (to the proxy), sends the request, and only
then the proxy cuts the connection. `httpx.ReadError` instead of `ConnectError`,
which my `call_downstream` did not handle, so users got 500 instead of 503.
Predicted before running the tests (except for the exact exception name).

**Question:** the request is "pay 1000 CZK" and you get ReadError. Is it safe to
retry automatically?

- *My answer:* no, you could pay more than 1000 CZK. **Correct.**

**Idempotent** = repeating has the same effect as doing it once. GET (read) is,
POST (pay, create order) is not.

**Question:** does the same apply to a timeout?

- *My answer:* yes, do not resend if not GET. **Right, with one exception:**
  `ConnectTimeout` means the connection never opened, so the request was never
  sent and a retry is safe.

The one question that decides it: **was the request already sent?**
Not sent → always retry. Maybe processed → retry only idempotent methods.

Also learned: Python picks the **first** matching `except`, so the more specific
`ConnectTimeout` must come before its parent `TimeoutException`.

---

## 2026-10-15: Writing the watchdog (lease + asyncio loop)

**Threads or asyncio?** My first idea: threads. Works, but two threads touching the
"last heartbeat" variable need locks (race condition). The watchdog only *waits*, so
asyncio fits: one thread, tasks take turns at every `await`, no locks.

**Passing time in as `now`** makes the lease testable without sleeping.

**Remembering state:** the lease keeps `last_beat`, `timeout_s` and whether the reset
was already reported (one reset per expiry, re-armed by the next heartbeat).

**"Only once" + a failed reset = never again.** If Toxiproxy is down at that one
moment, nothing retries. Fix: the loop keeps `pending = True` until a reset succeeds
(the lease handles *time*, the loop handles *delivery*).

Mistakes I made:

1. `asyncio.sleep(...)` **without `await`**: it does nothing, so the loop never hands
   control back. The tests hung forever and even Ctrl+C did not work, because asyncio
   stops a task by cancelling it, which also needs the loop to yield. This is exactly
   the asyncio downside we wrote down when choosing it.
2. `continue` in `except` skipped the `sleep`, so a dead Toxiproxy would get thousands
   of reset attempts per second. `pass` falls through to the sleep.

Result on the lab: after `kill -9` of the fault CLI, the watchdog removed the fault
4.9 s later.

---

## 2026-10-15: EXP-002, predictions that contradict each other

Predicted for +300 ms in both directions: "p50 605 ms" **and** "all requests fail with
504". Both cannot be true: if every attempt times out after 0.5 s, orders makes all
3 attempts and the request takes 3 × 0.5 = 1.5 s (measured 1509.6 ms). Lesson: check
that the parts of a prediction agree with each other, and follow the request through
every retry, not just one attempt.

Also learned: a timeout turns gradual slowness into a sudden outage (a "cliff").

---

## 2026-10-16: Sprint 2 interview check

Multiple-choice quiz: **9/10** (missed: what the watchdog healthcheck checks).
Own-words questions:

- *What is the watchdog for?* Needed a reminder, then correct: a safety net that
  removes faults when their owner (the CLI) stops sending heartbeats.
- *What does its healthcheck check?* **Weak spot.** Mixed up what checks what. Each
  container's healthcheck checks only itself; the watchdog's checks that its background
  loop is still running. The point: a process can be alive and answer `200` while the
  part that does the real work is dead (liveness vs. actual function).
- *Why did +300 ms on the way back cause 100 % errors?* Correct on my own: 600 ms round
  trip > 0.5 s timeout on every attempt; with retries users wait 1.5 s for a 504. A
  timeout turns slowness into an outage.
- *Why retry GET but not POST after a ReadError?* Correct on my own: the request was
  already sent and the client cannot know whether the server processed it; repeating a
  POST could pay twice. (Term: GET is idempotent, POST is not.)

Revisit the watchdog healthcheck in the Sprint 3 check.

---

## 2026-10-18: Writing `_inject` (the inject phase of the runner)

Mistakes in my first version, all four caught by the tests or by pyright:

- **Missing `await`, second time** (first: `asyncio.sleep` in Sprint 2). Without it an
  `async` function is only prepared, never run. Pyright says so before the tests do
  (`"CoroutineType[...]" is not iterable`), so run `make check` first.
- **Possibly unbound variable.** If adding the fault fails, `faults = await ...` never
  assigns, and the cleanup loop in `finally` crashes with `UnboundLocalError`, which
  hides the real error. Fix: `faults = []` before `try`.
- **Removed from the wrong thing.** `faults.remove(f)` drops an item from a Python
  list; the toxic stays in Toxiproxy. The list is only a receipt of what was added.
- **Discarded the task handle.** `asyncio.create_task` returns the only way to cancel
  the task later, so heartbeats would have run forever and disabled the watchdog.

How to know what to call without reading the whole codebase: look at the class's
`__init__` (its toolbox), then at the signature of each thing I call: is it `async`?
What does it take? What does it return? Work backwards from what I need (here: a
`dict` to save) to who produces it.

---

## 2026-10-18: Writing `reconcile` (first function I designed myself)

Plan first, in words, then code. My first plan only looked for experiments in
`inject`; walking through "where can a crash happen?" found `pending`, `baseline` and
`recover` too. Lesson: list the scenarios before the code.

Python things I learned on the way:

- **A `set` cannot hold a `dict`** (or anything containing one). A set files items by
  their hash; if an item could change, its hash would change and the set would look in
  the wrong place. So only unchangeable things are hashable (`int`, `str`, `tuple`), and
  things that are equal must have the same hash, which is why it is not done by
  variable name or memory address for dataclasses.
- **A module-level name is not an attribute of an object.** `RUNNING` lives in the file
  `store.py`, not inside a `Store` object, so it is imported, not `store.RUNNING`.
- **`try` only catches what happens inside it.** I first wrapped the wrong lines; the
  traceback line number (`runner.py:103`) shows which line actually failed.
- **Each file has its own names.** An exception can fly in from `httpx` code, but to
  name it in `except` the file needs its own `import httpx`.
- **Read the pytest diff**: left is what my code returned, right is what the test
  expects.

---

## 2026-10-18: EXP-003, the difference that was time

The controller seemed to measure a shorter tail than the manual method (baseline p95
5.6 vs 11.9 ms). Three suspects, each tested by changing one thing: name resolution,
connection reuse, and finally *when* each was measured. Only the last one mattered: the
controller ran at 13:30 and the manual runs after 14:00, and the Mac drifted in between.
Run alternately, both measure the same.

- **Confounding variable:** when two things change at once (method *and* time), the
  result cannot say which one caused the difference.
- **Interleave A and B** (A, B, A, B …) so both see the same conditions.
- A wrong prediction that is tested is progress: it removes a suspect.
- Choosing "investigate now" instead of "issue for later" changed the conclusion; with
  the issue we would still believe the controller measures differently.

---

## 2026-10-18: Sprint 3 interview check

Multiple-choice quiz: **10/10** (including the watchdog healthcheck, missed last time).
Own-words questions:

- *What does the watchdog's healthcheck check?* The reason on my own: a watchdog that
  looks healthy but does nothing would leave faults behind. Needed the precise *what*:
  that the `watch` loop is still running, not only that the process answers HTTP.
- *`kill -9` of the controller mid-experiment: what happens to the fault and the
  record?* Reconcile on restart on my own. **Weak spot:** first said the fault stays
  until the restart. The watchdog removes it about 5 s after the last heartbeat, whether
  or not the controller ever restarts. It knows nothing about faults, only when the last
  heartbeat came (a dead man's switch). Whichever layer comes first cleans up. Retold
  correctly at the end.
- *Why did the controller seem to measure a shorter tail (EXP-003)?* On my own: tested
  hypotheses one at a time; it was the time of measurement. Correction: the methods ran
  alternately, not at the same time. (Terms: confounding variable, interleaving.)
- *Why is the load target not in the request?* On my own: so that anyone who reaches
  the API cannot use it for a DoS. Also SSRF; trust boundary.

Revisit the controller-crash timeline (watchdog vs. reconcile) in the Sprint 4 check.
