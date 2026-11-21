from chaosnet.dataset import COLUMNS, rows

BEGAN = {"baseline": 100.0, "inject": 110.4, "recover": 125.4, "completed": 135.4}


def test_seconds_are_labelled_by_the_phase_they_fell_in() -> None:
    numbers = {t: {"orders-inventory p95_ms": 5.0} for t in range(100, 136)}
    out = rows(7, "orders-inventory", {"kind": "latency", "ms": 100}, BEGAN, numbers)
    assert [r["second"] for r in out] == list(range(36))
    assert {r["phase"] for r in out[:11]} == {"baseline"}  # 100..110, before 110.4
    assert {r["phase"] for r in out[11:26]} == {"inject"}  # 111..125
    assert {r["phase"] for r in out[26:]} == {"recover"}
    assert [r["fault"] for r in out].count(1) == 15
    assert {r["fault_link"] for r in out if r["fault"]} == {"orders-inventory"}
    assert {r["fault_link"] for r in out if not r["fault"]} == {""}
    assert out[0]["run"] == 7 and out[0]["kind"] == "latency" and out[0]["strength"] == 100


def test_a_link_without_attempts_has_no_latency() -> None:
    nan = float("nan")
    out = rows(
        1, "gateway-orders", {"kind": "reset_peer"}, BEGAN, {100: {"gateway-orders p95_ms": nan}}
    )
    assert "gateway-orders p95_ms" not in out[0]
    assert out[0]["strength"] == ""
    assert set(out[0]) <= set(COLUMNS)
