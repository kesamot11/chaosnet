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
