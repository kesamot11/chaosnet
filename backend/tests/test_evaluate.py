from chaosnet.evaluate import folds, measure, rule

# 10 runs of 35 seconds, like data/runs.csv
ROWS = [{"run": run, "second": s} for run in range(26, 36) for s in range(35)]


def test_a_run_is_never_on_both_sides_of_a_split() -> None:
    for train, test in folds(ROWS):
        assert {ROWS[i]["run"] for i in train}.isdisjoint({ROWS[i]["run"] for i in test})


def test_every_second_is_tested_exactly_once() -> None:
    tested = sorted(i for _, test in folds(ROWS) for i in test)
    assert tested == list(range(len(ROWS)))


def second(fault_link: str = "", **numbers: float) -> dict[str, object]:
    """One labelled second; numbers like gateway_orders_p95_ms=20."""
    row: dict[str, object] = {"run": "1", "second": "0", "fault": "1" if fault_link else "0"}
    row["fault_link"] = fault_link
    for key, value in numbers.items():
        link, column = key.split("__")
        row[f"{link.replace('_', '-')} {column}"] = str(value)
    return row


def test_a_quiet_second_is_no_alarm() -> None:
    assert rule(second(gateway_orders__p95_ms=20, orders_inventory__p95_ms=9)) is None


def test_a_slow_callee_is_blamed_not_the_waiting_caller() -> None:
    row = second(gateway_orders__p95_ms=495, orders_inventory__p95_ms=495)
    assert rule(row) == "orders-inventory"


def test_a_failed_attempt_is_a_problem_even_when_fast() -> None:  # reset_peer
    assert rule(second(gateway_orders__connection_error=40, gateway_orders__p95_ms=9)) == (
        "gateway-orders"
    )


def test_an_empty_cell_counts_as_nothing() -> None:
    row = second(gateway_orders__p95_ms=20)
    row["orders-inventory timeout"] = ""
    assert rule(row) is None


def test_the_four_numbers() -> None:
    rows = [
        {**second(), "run": "1", "second": "0"},  # normal, no alarm
        {**second(gateway_orders__p95_ms=200), "run": "1", "second": "1"},  # false alarm
        {**second("orders-inventory"), "run": "2", "second": "10"},  # missed
        {**second("orders-inventory", orders_inventory__timeout=5), "run": "2", "second": "11"},
        {**second("orders-inventory", gateway_orders__p95_ms=900), "run": "2", "second": "12"},
    ]
    m = measure(rows, rule)
    assert m["precision"] == 2 / 3
    assert m["recall"] == 2 / 3
    assert m["detection delay s (median)"] == 1
    assert m["runs never detected"] == 0
    assert m["root-cause accuracy"] == 1 / 2  # the second true alarm blamed the caller
