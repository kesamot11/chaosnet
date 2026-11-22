from chaosnet.evaluate import folds

# 10 runs of 35 seconds, like data/runs.csv
ROWS = [{"run": run, "second": s} for run in range(26, 36) for s in range(35)]


def test_a_run_is_never_on_both_sides_of_a_split() -> None:
    for train, test in folds(ROWS):
        assert {ROWS[i]["run"] for i in train}.isdisjoint({ROWS[i]["run"] for i in test})


def test_every_second_is_tested_exactly_once() -> None:
    tested = sorted(i for _, test in folds(ROWS) for i in test)
    assert tested == list(range(len(ROWS)))
