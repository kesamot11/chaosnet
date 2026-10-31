"""Every arrow of the drawing in ADR-008 (#135)."""

from chaosnet_lab.breaker import Breaker


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def calls(b: Breaker, *outcomes: bool, every_s: float = 0.1) -> None:
    """Make one call per outcome, `every_s` apart, each allowed first."""
    clock = b.now
    assert isinstance(clock, Clock)
    for ok in outcomes:
        assert b.allow()
        b.record(ok)
        clock.t += every_s


def breaker() -> tuple[Breaker, Clock]:
    clock = Clock()
    return Breaker(now=clock), clock


# --- step 2: allow() --------------------------------------------------------------------


def test_a_new_breaker_is_closed_and_allows_calls() -> None:
    b, _ = breaker()
    assert b.state == "closed"
    assert b.allow()


def test_an_open_breaker_refuses_calls_until_the_cooldown_has_passed() -> None:
    b, clock = breaker()
    b.state, b.opened_at = "open", clock.t
    clock.t += 4.9
    assert not b.allow()
    clock.t += 0.2  # 5.1 s after opening
    assert b.allow()
    assert b.state == "half_open"


def test_half_open_lets_exactly_one_trial_call_through() -> None:
    b, clock = breaker()
    b.state, b.opened_at = "open", clock.t - 6
    assert b.allow()  # the trial
    assert not b.allow()  # a second request while the trial is on its way
    assert not b.allow()


# --- step 3: record() -------------------------------------------------------------------


def test_more_than_half_failing_opens_it() -> None:
    b, _ = breaker()
    calls(b, *[True] * 4, *[False] * 6)  # 6 of 10 failed
    assert b.state == "open"
    assert not b.allow()


def test_exactly_half_failing_keeps_it_closed() -> None:
    b, _ = breaker()
    calls(b, *[True] * 5, *[False] * 5)
    assert b.state == "closed"


def test_one_good_two_bad_repeated_opens_it() -> None:
    # never more than two failures in a row, but 6 of 10 fail (Tomáš's case)
    b, _ = breaker()
    calls(b, *[True, False, False] * 3, True)
    assert b.state == "open"


def test_fewer_calls_than_the_minimum_never_open_it() -> None:
    # the single failure at night (Tomáš's false alarm)
    b, _ = breaker()
    calls(b, False)
    calls(b, *[False] * 8)
    assert b.state == "closed"  # 9 calls, all failed: still below the minimum of 10


def test_old_calls_leave_the_window() -> None:
    b, clock = breaker()
    calls(b, *[False] * 9)  # 9 failures ...
    clock.t += 11  # ... more than 10 s ago
    calls(b, *[True] * 9, False)  # 10 calls in the window, 1 failed
    assert b.state == "closed"


def test_a_successful_trial_closes_it_with_a_fresh_window() -> None:
    b, clock = breaker()
    calls(b, *[False] * 10)
    assert b.state == "open"
    clock.t += 5.1
    calls(b, True)  # the trial
    assert b.state == "closed"
    calls(b, False)  # the old failures do not count any more: one failure, one call
    assert b.state == "closed"


def test_a_failed_trial_opens_it_again_for_a_full_cooldown() -> None:
    b, clock = breaker()
    calls(b, *[False] * 10)
    clock.t += 5.1
    calls(b, False)  # the trial fails; calls() then moves the clock 0.1 s on
    assert b.state == "open"
    clock.t += 4.8  # 4.9 s after the failed trial
    assert not b.allow()
    clock.t += 0.2
    assert b.allow()
