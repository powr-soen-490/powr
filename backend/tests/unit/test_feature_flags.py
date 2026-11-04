# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Tests for backend Flagsmith evaluation and route protection."""

import pytest
from fastapi import HTTPException
from flagsmith.exceptions import FlagsmithClientError
from pydantic import SecretStr
from requests import RequestException

from app.core.config import Settings
from app.core.feature_flags import (
    FeatureFlagsUnavailableError,
    _disabled_flag,
    _get_flagsmith_client,
    is_feature_enabled,
    require_feature,
)

TEST_DATABASE_URL = "postgresql://localhost:5432/powr_test"


class StubFlags:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def is_feature_enabled(self, _feature_name: str) -> bool:
        return self.enabled


class StubFlagsmith:
    def __init__(self, enabled: bool) -> None:
        self.flags = StubFlags(enabled)

    def get_environment_flags(self) -> StubFlags:
        return self.flags


def test_is_feature_enabled_uses_the_configured_server_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        _env_file=None,
        database_url=TEST_DATABASE_URL,
        flagsmith_server_side_key=SecretStr("server-key"),
    )
    monkeypatch.setattr(
        "app.core.feature_flags._get_flagsmith_client",
        lambda _key, _url: StubFlagsmith(True),
    )

    assert is_feature_enabled("page_inventory", settings)


def test_is_feature_enabled_rejects_a_blank_server_key() -> None:
    settings = Settings(
        _env_file=None,
        database_url=TEST_DATABASE_URL,
        flagsmith_server_side_key=SecretStr("  "),
    )

    with pytest.raises(FeatureFlagsUnavailableError, match="FLAGSMITH_SERVER_SIDE_KEY"):
        is_feature_enabled("page_inventory", settings)


def test_flagsmith_client_uses_timeout_and_a_disabled_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    options: dict[str, object] = {}

    class StubClient:
        def __init__(self, **kwargs: object) -> None:
            options.update(kwargs)

    monkeypatch.setattr("app.core.feature_flags.Flagsmith", StubClient)
    _get_flagsmith_client.cache_clear()
    try:
        _get_flagsmith_client("server-key", "https://flags.example/api/")
    finally:
        _get_flagsmith_client.cache_clear()

    assert options == {
        "environment_key": "server-key",
        "api_url": "https://flags.example/api/",
        "request_timeout_seconds": 5,
        "default_flag_handler": _disabled_flag,
    }
    flag = _disabled_flag("unknown")
    assert flag.enabled is False
    assert flag.value is None


def test_is_feature_enabled_wraps_flagsmith_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        _env_file=None,
        database_url=TEST_DATABASE_URL,
        flagsmith_server_side_key=SecretStr("server-key"),
    )

    class FailedFlags:
        def get_environment_flags(self) -> None:
            raise FlagsmithClientError("request failed")

    class FailedClient:
        def get_environment_flags(self) -> FailedFlags:
            return FailedFlags()

    monkeypatch.setattr(
        "app.core.feature_flags._get_flagsmith_client",
        lambda _key, _url: FailedClient(),
    )

    with pytest.raises(FeatureFlagsUnavailableError, match="could not evaluate") as exc_info:
        is_feature_enabled("page_inventory", settings)

    assert isinstance(exc_info.value.__cause__, FlagsmithClientError)


def test_is_feature_enabled_wraps_request_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        _env_file=None,
        database_url=TEST_DATABASE_URL,
        flagsmith_server_side_key=SecretStr("server-key"),
    )

    class FailedFlags:
        def get_environment_flags(self) -> None:
            raise RequestException("connection failed")

    class FailedClient:
        def get_environment_flags(self) -> FailedFlags:
            return FailedFlags()

    monkeypatch.setattr(
        "app.core.feature_flags._get_flagsmith_client",
        lambda _key, _url: FailedClient(),
    )

    with pytest.raises(FeatureFlagsUnavailableError, match="could not evaluate") as exc_info:
        is_feature_enabled("page_inventory", settings)

    assert isinstance(exc_info.value.__cause__, RequestException)


def test_feature_flag_evaluation_requires_a_server_key() -> None:
    settings = Settings(_env_file=None, database_url=TEST_DATABASE_URL)

    with pytest.raises(FeatureFlagsUnavailableError, match="FLAGSMITH_SERVER_SIDE_KEY"):
        is_feature_enabled("page_inventory", settings)


def test_require_feature_hides_disabled_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        _env_file=None,
        database_url=TEST_DATABASE_URL,
        flagsmith_server_side_key=SecretStr("server-key"),
    )
    monkeypatch.setattr(
        "app.core.feature_flags.is_feature_enabled",
        lambda _name, _settings: False,
    )

    with pytest.raises(HTTPException) as exc_info:
        require_feature("page_inventory")(settings)

    assert exc_info.value.status_code == 404


def test_require_feature_allows_enabled_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        _env_file=None,
        database_url=TEST_DATABASE_URL,
        flagsmith_server_side_key=SecretStr("server-key"),
    )
    monkeypatch.setattr(
        "app.core.feature_flags.is_feature_enabled",
        lambda _name, _settings: True,
    )

    assert require_feature("page_inventory")(settings) is None


def test_require_feature_fails_closed_when_flagsmith_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        _env_file=None,
        database_url=TEST_DATABASE_URL,
        flagsmith_server_side_key=SecretStr("server-key"),
    )

    def unavailable(_name: str, _settings: Settings) -> bool:
        raise FeatureFlagsUnavailableError("unavailable")

    monkeypatch.setattr("app.core.feature_flags.is_feature_enabled", unavailable)

    with pytest.raises(HTTPException) as exc_info:
        require_feature("page_inventory")(settings)

    assert exc_info.value.status_code == 503
