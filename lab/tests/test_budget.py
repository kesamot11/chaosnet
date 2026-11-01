"""Retry budget (#138)."""

import pytest

from chaosnet_lab.budget import RetryBudget


def test_a_new_budget_is_full() -> None:
    b = RetryBudget(cap=3)
    assert [b.try_retry() for _ in range(4)] == [True, True, True, False]


def test_ten_first_attempts_pay_for_one_retry() -> None:
    b = RetryBudget(ratio=0.1, cap=10)
    b.tokens = 0
    for _ in range(9):
        b.first_attempt()
    assert not b.try_retry()  # 0.9 tokens: not enough
    b.first_attempt()
    assert b.try_retry()  # 1.0
    assert not b.try_retry()


def test_tokens_never_exceed_the_cap() -> None:
    b = RetryBudget(ratio=0.1, cap=2)
    for _ in range(1000):
        b.first_attempt()
    assert b.tokens == pytest.approx(2)


def test_a_failed_try_takes_nothing() -> None:
    b = RetryBudget()
    b.tokens = 0.5
    assert not b.try_retry()
    assert b.tokens == pytest.approx(0.5)
