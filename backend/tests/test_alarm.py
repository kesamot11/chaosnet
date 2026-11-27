import asyncio
import csv
from typing import Any

import httpx

from chaosnet import alarm
from chaosnet.dataset import LINKS


def test_it_knows_only_the_recorded_lab_and_load() -> None:
    assert alarm.knows(set(LINKS), 20)
    assert not alarm.knows(set(LINKS), 50)  # a load it never saw (#273)
    assert not alarm.knows({*LINKS, "orders-payments"}, 20)  # a link it never saw (#272)


def test_the_numbers_now_come_in_the_recorded_columns() -> None:
    def prometheus(request: httpx.Request) -> httpx.Response:
        query = request.url.params["query"]
        if "lab_attempts_total" in query:
            result = [{"metric": {"hop": "orders->inventory", "outcome": "ok"}, "value": [1, "20"]}]
        else:  # p50 and p95; gateway->orders had no attempts, so NaN
            result = [
                {"metric": {"hop": "orders->inventory"}, "value": [1, "8.5"]},
                {"metric": {"hop": "gateway->orders"}, "value": [1, "NaN"]},
            ]
        return httpx.Response(200, json={"data": {"result": result}})

    async def go() -> dict[str, Any]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(prometheus)) as c:
            return await alarm.now(c, "http://prometheus")

    assert asyncio.run(go()) == {
        "orders-inventory ok": 20.0,
        "orders-inventory p50_ms": 8.5,
        "orders-inventory p95_ms": 8.5,
    }


def test_the_tree_names_a_recorded_fault_and_stays_quiet_on_a_normal_second() -> None:
    with open(alarm.RUNS, newline="") as f:
        rows = list(csv.DictReader(f))
    model = alarm.train()
    slow = next(
        r for r in rows if r["kind"] == "latency" and r["strength"] == "200" and r["second"] == "17"
    )
    quiet = next(r for r in rows if r["phase"] == "baseline")
    assert alarm.answer(model, slow) == slow["fault_link"]
    assert alarm.answer(model, quiet) is None
