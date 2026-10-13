import pytest

from chaosnet_lab.relay import Hop

VALID = {"DOWNSTREAM_URL": "http://inventory:8000", "TIMEOUT_S": "0.5", "MAX_RETRIES": "2"}


def hop_from(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> Hop:
    for key, value in {**VALID, **overrides}.items():
        monkeypatch.setenv(key, value)
    return Hop.from_env("orders->inventory")


def test_valid_config(monkeypatch: pytest.MonkeyPatch) -> None:
    assert hop_from(monkeypatch) == Hop("orders->inventory", "http://inventory:8000", 0.5, 2)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("DOWNSTREAM_URL", ""),
        ("DOWNSTREAM_URL", "inventory:8000"),
        ("DOWNSTREAM_URL", "htp://inventory:8000"),
        ("DOWNSTREAM_URL", "http://"),
        ("TIMEOUT_S", "0"),
        ("MAX_RETRIES", "-1"),
    ],
)
def test_invalid_config_fails_at_startup(
    monkeypatch: pytest.MonkeyPatch, key: str, value: str
) -> None:
    with pytest.raises(ValueError, match=key):
        hop_from(monkeypatch, **{key: value})
