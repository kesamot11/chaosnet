"""The live alarm (#257, ADR-013 decision 9): the tree of EXP-011 on the lab, every second.

It asks Prometheus the same queries the labelled runs were recorded with (dataset.py), so
the numbers it gets are computed exactly like the ones the tree learned from.
"""

import csv
from pathlib import Path

import httpx
from sklearn.tree import DecisionTreeClassifier  # pyright: ignore[reportMissingTypeStubs]

from chaosnet.dataset import FEATURES, LINKS, QUERIES, column
from chaosnet.evaluate import NONE, Row, number, tree

RUNS = Path(__file__).parents[3] / "data" / "runs.csv"
RATE = 20  # req/s of every recorded run; another load is data the tree never saw (#273)


def knows(links: set[str], rate: float) -> bool:
    """Whether the tree has seen this lab and this load; if not, it doesn't guess."""
    return links == set(LINKS) and rate == RATE


def train(path: Path = RUNS) -> DecisionTreeClassifier:
    """The tree from every recorded run; holding bandwidth 16 out was only for measuring."""
    with open(path, newline="") as f:
        return tree(list(csv.DictReader(f)))


async def now(client: httpx.AsyncClient, prometheus: str) -> Row:
    """The lab's numbers right now, in the columns of data/runs.csv."""
    row: Row = {}
    for name, query in QUERIES.items():
        res = await client.get(f"{prometheus}/api/v1/query", params={"query": query})
        res.raise_for_status()
        for series in res.json()["data"]["result"]:
            value = float(series["value"][1])
            if value == value:  # NaN when a link had no attempts: an empty cell, as recorded
                row[column(name, series["metric"])] = value
    return row


def answer(model: DecisionTreeClassifier, row: Row) -> str | None:
    """The link the tree names for these numbers, None when it sees no fault."""
    x = [[number(row, c) for c in FEATURES]]
    link = str(model.predict(x)[0])  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    return None if link == NONE else link
