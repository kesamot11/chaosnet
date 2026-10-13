# Architecture

> The component overview, request flow and diagrams are added in #16. This file
> currently only records verified assumptions about the execution environment.

## Verified environment assumptions

Spike #12, run on 2026-10-13. Everything below was measured with the commands
listed. Nothing was taken from documentation alone.

### Environment

| | |
|---|---|
| Host | Apple Silicon Mac (arm64), macOS 26.6 |
| Docker Desktop | 4.95.0 |
| Docker Engine / client | 29.8.2, linux/arm64 |
| Docker Compose | v5.6.0 |
| Docker VM | kernel `7.0.14-linuxkit`, 10 CPUs, ~7.7 GiB RAM |

All images used run natively on arm64: `ghcr.io/shopify/toxiproxy:2.12.0`,
`python:3.14-slim`, `alpine:3.22`.

### Toxiproxy

Setup: `curl` on the Mac, then a published port, then Toxiproxy, then a
`python -m http.server` upstream container on a user-defined bridge network.
Five sequential requests per case:

| Case | `curl` time_total (s) |
|---|---|
| No toxic | 0.0008–0.0014 |
| `latency` 300 ms, `downstream` | 0.303–0.309 |
| `latency` 300 ms on both `downstream` and `upstream` | 0.607–0.613 |
| After `POST /reset` | 0.0017–0.0022 |

Findings:

- A latency toxic delays one direction only. A delay on both streams adds up.
  To model a link with RTT *x*, apply *x*/2 per direction, or *x* on one
  direction, and document which.
- Measured latency exceeded the configured value by about 2–8 ms in this
  setup.
- `POST /reset` returns `204` and removes all toxics while keeping proxies. The
  ADR-001 watchdog can rely on it.
- **Restarting the Toxiproxy container deletes all proxies, not just toxics**
  (`GET /proxies` returned `{}` after `docker restart`). Consequences:
  - the watchdog must use `POST /reset`, never a container restart, to clear
    faults;
  - proxy definitions must be recreated idempotently on every Toxiproxy start
    (for example with a `-config` file), or the services behind them become
    unreachable.

### tc netem

| Case | `ping` RTT avg (ms), 5 packets |
|---|---|
| Container to container, no qdisc | 0.17 |
| `tc qdisc add dev eth0 root netem delay 100ms` on the pinging container | 103.6 (min 101.2, max 105.4) |
| After `tc qdisc del` | 0.20 |

Findings:

- `sch_netem` is available in the Docker Desktop VM kernel and works inside a
  container with `--cap-add NET_ADMIN`.
- Without `NET_ADMIN` it fails with `RTNETLINK answers: Operation not
  permitted`, so the capability gate works as expected.
- The measured delay exceeded the configured value by 1–5 ms. Netem results are
  emulation in a VM, not physical network behaviour.

### Host reachability

| Target from the Mac | Result |
|---|---|
| Published port `127.0.0.1:8474` | HTTP 200 |
| Container IP `172.18.0.2:8000` | unreachable (curl timeout after 3 s) |

This confirms the networking rule: the control plane reaches the lab only
through published ports and the Docker API, never through container IPs.

### Docker DNS and paused containers

Verified in #13 on the demo lab.

- Services resolve each other through Docker's embedded DNS (`inventory` resolved to
  `172.18.0.2` from inside `orders`).
- After `docker stop inventory`, the name no longer resolves at all:
  `gaierror [Errno -2] Name or service not known`. The caller sees a name
  resolution failure, not "connection refused", and it fails fast (gateway answered
  503 in ~10 ms).
- `docker pause` freezes the processes. Callers get no answer and hang until
  their timeout (504 after 1.52 s with a 0.5 s timeout and 2 retries). Not yet
  verified at packet level whether new TCP handshakes still complete (the kernel
  keeps running) or only pooled keep-alive connections are affected.
- **A paused container is reported as `unhealthy` immediately**, and stays
  unhealthy after `docker unpause` until its next successful probe (up to one
  healthcheck interval). During that window `docker compose up --wait` refuses to
  start services that depend on it. The control plane must not treat Docker health
  as ground truth during or right after a pause fault.

### Not verified yet

- Behaviour under load (all measurements above are five sequential requests).
- Netem on interfaces of containers other than the one running `tc`, for example
  from a sidecar sharing the network namespace. Needed in M8.
