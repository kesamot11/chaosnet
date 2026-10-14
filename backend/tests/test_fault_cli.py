import asyncio

import httpx
import pytest
from fakes import API, LINK, FakeToxiproxy

from chaosnet.fault_cli import fault_from_args, hold_faults, main, parse_args
from chaosnet.faults import FaultDriver

WATCHDOG = "http://watchdog:8475"


class Lab:
    """Fake Toxiproxy plus a fake watchdog that counts heartbeats."""

    def __init__(self, watchdog_up: bool = True) -> None:
        self.toxiproxy = FakeToxiproxy()
        self.watchdog_up = watchdog_up
        self.heartbeats = 0

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "watchdog":
            if not self.watchdog_up:
                raise httpx.ConnectError("refused")
            self.heartbeats += 1
            return httpx.Response(204)
        return self.toxiproxy.handle(request)


async def hold(lab: Lab, *, duration_s: float, cancel_after_s: float | None = None) -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(lab.handle)) as client:
        task = asyncio.create_task(
            hold_faults(
                FaultDriver(client, API),
                client,
                lambda d: d.add_latency(LINK, 300, "both"),
                duration_s=duration_s,
                watchdog_url=WATCHDOG,
                interval_s=0.05,
            )
        )
        if cancel_after_s is not None:
            await asyncio.sleep(cancel_after_s)
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def test_fault_is_active_while_held_and_removed_after_duration() -> None:
    lab = Lab()

    async def check_midway() -> None:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(hold(lab, duration_s=0.3))
            await asyncio.sleep(0.1)
            assert len(lab.toxiproxy.toxics[LINK]) == 2

    asyncio.run(check_midway())
    assert lab.toxiproxy.toxics[LINK] == []


def test_heartbeat_is_sent_every_interval() -> None:
    lab = Lab()
    asyncio.run(hold(lab, duration_s=0.3))
    assert 5 <= lab.heartbeats <= 7  # 0.3 s / 0.05 s


def test_cancel_like_ctrl_c_removes_the_fault_immediately() -> None:
    lab = Lab()
    asyncio.run(hold(lab, duration_s=60, cancel_after_s=0.1))
    assert lab.toxiproxy.toxics[LINK] == []


def test_unreachable_watchdog_does_not_stop_the_fault_or_its_cleanup() -> None:
    lab = Lab(watchdog_up=False)
    asyncio.run(hold(lab, duration_s=0.2))
    assert lab.heartbeats == 0
    assert lab.toxiproxy.toxics[LINK] == []


def test_arguments_map_to_the_right_fault() -> None:
    lab = Lab()
    args = parse_args(
        ["latency", "--link", LINK, "--ms", "250", "--direction", "request", "--duration", "5"]
    )

    async def apply() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lab.handle)) as client:
            await fault_from_args(args)(FaultDriver(client, API))

    asyncio.run(apply())
    [toxic] = lab.toxiproxy.toxics[LINK]
    assert (toxic["stream"], toxic["attributes"]["latency"]) == ("upstream", 250)


def test_user_errors_print_one_line_not_a_traceback(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "sys.argv", ["chaosnet-fault", "latency", "--link", LINK, "--ms", "-5", "--duration", "1"]
    )
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    assert capsys.readouterr().err == "error: Latency must be > 0 ms, got -5\n"
