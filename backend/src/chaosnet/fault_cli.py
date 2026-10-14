"""Command line for faults: apply one for a fixed time, then always remove it.

    uv run chaosnet-fault latency --link orders-inventory --ms 300 --direction both --duration 60
    uv run chaosnet-fault list
    uv run chaosnet-fault clear

Cleanup (ADR-001): the fault is removed when the duration ends, on Ctrl+C and on
SIGTERM (layer 1). While it is active, a heartbeat goes to the watchdog every second,
so the watchdog removes it if this process dies without cleaning up (layer 3).
"""

import argparse
import asyncio
import os
import signal
import sys
from collections.abc import Awaitable, Callable
from datetime import datetime

import httpx

from chaosnet.faults import Fault, FaultDriver, FaultError

AddFault = Callable[[FaultDriver], Awaitable[list[Fault]]]


def log(message: str) -> None:
    print(f"{datetime.now():%H:%M:%S} {message}", flush=True)


async def hold_faults(
    driver: FaultDriver,
    client: httpx.AsyncClient,
    add: AddFault,
    *,
    duration_s: float,
    watchdog_url: str,
    interval_s: float = 1.0,
) -> None:
    """Apply faults, keep the watchdog lease alive for ``duration_s``, then remove them."""
    faults = await add(driver)
    log(f"applied {', '.join(f'{f.link}/{f.name} {f.attributes}' for f in faults)}")
    try:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + duration_s
        watchdog_ok = True
        while (remaining := deadline - loop.time()) > 0:
            ok = await send_heartbeat(client, watchdog_url)
            if ok != watchdog_ok:
                log(
                    "watchdog reachable again"
                    if ok
                    else "WARNING: watchdog unreachable, a crash "
                    "of this process would leave the fault active"
                )
                watchdog_ok = ok
            await asyncio.sleep(min(interval_s, remaining))
    finally:
        for fault in faults:
            await driver.remove(fault)
        log(f"removed {len(faults)} fault(s)")


async def send_heartbeat(client: httpx.AsyncClient, watchdog_url: str) -> bool:
    try:
        res = await client.post(f"{watchdog_url}/heartbeat", timeout=0.5)
        return not res.is_error
    except httpx.TransportError:
        return False


def fault_from_args(args: argparse.Namespace) -> AddFault:
    if args.kind == "latency":
        return lambda d: d.add_latency(args.link, args.ms, args.direction)
    if args.kind == "bandwidth":
        return lambda d: d.add_bandwidth(args.link, args.kbps, args.direction)
    return lambda d: d.add_reset_peer(args.link, args.direction)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="chaosnet-fault", description="Apply a fault for a fixed time, then remove it."
    )
    parser.add_argument(
        "--toxiproxy", default=os.environ.get("TOXIPROXY_URL", "http://127.0.0.1:8474")
    )
    parser.add_argument(
        "--watchdog", default=os.environ.get("WATCHDOG_URL", "http://127.0.0.1:8475")
    )
    sub = parser.add_subparsers(dest="kind", required=True)

    def fault_command(name: str, default_direction: str) -> argparse.ArgumentParser:
        p = sub.add_parser(name)
        p.add_argument("--link", required=True, help="e.g. orders-inventory")
        p.add_argument(
            "--direction", choices=["request", "response", "both"], default=default_direction
        )
        p.add_argument("--duration", type=float, required=True, help="seconds")
        return p

    fault_command("latency", "both").add_argument("--ms", type=int, required=True)
    fault_command("bandwidth", "both").add_argument("--kbps", type=int, required=True)
    fault_command("reset_peer", "response")
    sub.add_parser("list")
    sub.add_parser("clear")
    return parser.parse_args(argv)


async def run(args: argparse.Namespace) -> None:
    # Ctrl+C and plain `kill` cancel the task, so the `finally` cleanup runs. SIGINT is
    # registered explicitly: a process started in the background by a script inherits
    # SIGINT as *ignored* and would otherwise run on until the duration ends.
    task = asyncio.current_task()
    assert task is not None
    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(sig, task.cancel)

    async with httpx.AsyncClient() as client:
        driver = FaultDriver(client, args.toxiproxy)
        if args.kind == "list":
            for f in await driver.list_faults():
                print(f"{f.link}\t{f.name}\t{f.direction}\t{f.attributes}")
        elif args.kind == "clear":
            await driver.remove_all()
            log("removed all faults")
        else:
            await hold_faults(
                driver,
                client,
                fault_from_args(args),
                duration_s=args.duration,
                watchdog_url=args.watchdog,
            )


def main() -> None:
    try:
        asyncio.run(run(parse_args(sys.argv[1:])))
    except KeyboardInterrupt, asyncio.CancelledError:
        sys.exit(130)
    except (FaultError, ValueError, httpx.TransportError) as e:
        # A typo in --link or an unreachable Toxiproxy is a user error, not a crash.
        print(f"error: {str(e).strip() or type(e).__name__}", file=sys.stderr)
        sys.exit(1)
