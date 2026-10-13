import pytest

from chaosnet.stats import percentile

# The textbook nearest-rank example (5 samples).
FIVE = [15.0, 20.0, 35.0, 40.0, 50.0]


@pytest.mark.parametrize(
    ("p", "expected"),
    [(5, 15.0), (30, 20.0), (40, 20.0), (50, 35.0), (100, 50.0)],
)
def test_textbook_example(p: float, expected: float) -> None:
    assert percentile(FIVE, p) == expected


def test_unsorted_input_and_caller_list_untouched() -> None:
    samples = [50.0, 15.0, 40.0, 20.0, 35.0]
    assert percentile(samples, 50) == 35.0
    assert samples == [50.0, 15.0, 40.0, 20.0, 35.0]


def test_single_sample_is_every_percentile() -> None:
    assert percentile([7.0], 1) == 7.0
    assert percentile([7.0], 99.9) == 7.0


@pytest.mark.parametrize(("p", "expected"), [(50, 50.0), (95, 95.0), (99, 99.0), (100, 100.0)])
def test_one_to_hundred(p: float, expected: float) -> None:
    assert percentile([float(x) for x in range(1, 101)], p) == expected


@pytest.mark.parametrize(
    ("p", "n", "expected"), [(14, 100, 14.0), (28, 25, 7.0), (99.9, 1000, 999.0)]
)
def test_rank_is_not_broken_by_float_rounding(p: float, n: int, expected: float) -> None:
    assert percentile([float(x) for x in range(1, n + 1)], p) == expected


def test_coordinated_omission_example_from_the_chat() -> None:
    # Closed-loop tool during a 2 s freeze: 80 fast samples and a single slow one.
    samples = [5.0] * 80 + [2000.0]
    assert percentile(samples, 95) == 5.0  # the freeze is invisible at p95
    assert percentile(samples, 100) == 2000.0


def test_empty_samples_rejected() -> None:
    with pytest.raises(ValueError):
        percentile([], 50)


@pytest.mark.parametrize("p", [0, -1, 100.1])
def test_p_out_of_range_rejected(p: float) -> None:
    with pytest.raises(ValueError):
        percentile([1.0, 2.0], p)
