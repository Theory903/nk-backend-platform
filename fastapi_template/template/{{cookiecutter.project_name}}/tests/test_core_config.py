import pytest
from pydantic import Field  # noqa: F401 - re-exported via cfg_field in kernel

from {{cookiecutter.project_name}}.core.config import BaseConfig, cfg_field


class Engine(BaseConfig):
    dsn: str | None = None
    host: str | None = cfg_field(default=None, one_of="dsn_or_url")
    url: str | None = cfg_field(default=None, one_of="dsn_or_url")
    retries: int = 2


def test_extra_fields_are_forbidden() -> None:
    with pytest.raises(ValueError, match="retriesx"):
        Engine(retriesx=3)  # type: ignore[call-arg]


def test_one_of_requires_exactly_one() -> None:
    with pytest.raises(ValueError, match="exactly one of"):
        Engine(retries=1)

    with pytest.raises(ValueError, match="exactly one of"):
        Engine(host="h", url="u")

    ok = Engine(host="h")
    assert ok.host == "h" and ok.url is None


def test_pretty_print_is_yaml() -> None:
    dumped = Engine(host="postgres://x").pretty_print()

    assert "host:" in dumped and "postgres://x" in dumped
