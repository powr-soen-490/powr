# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Unit tests for settings validation."""

import pytest
from pydantic import ValidationError

from app.core.config import DEV_SESSION_SECRET_KEY, Settings

DATABASE_URL = "postgresql://powr:powr@localhost:5432/powr"
PRIVATE_SECRET = "a-private-secret-that-is-not-the-committed-default"


@pytest.mark.parametrize(
    "database_url",
    ["not-a-url", "mysql://user:password@localhost:3306/powr", ""],
)
def test_rejects_database_urls_that_are_not_postgres(database_url: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url=database_url)


def test_rejects_unknown_log_level() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url=DATABASE_URL,
            log_level="VERBOSE",
        )


def test_reads_cors_origins_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("CORS_ORIGINS", '["https://powr.example.com", "http://localhost:3000"]')

    settings = Settings(_env_file=None)

    assert settings.cors_origins == ["https://powr.example.com", "http://localhost:3000"]


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_rejects_the_dev_session_secret_when_deployed(environment: str) -> None:
    with pytest.raises(ValidationError, match="SESSION_SECRET_KEY"):
        Settings(
            _env_file=None,
            database_url=DATABASE_URL,
            environment=environment,
            cookie_secure=True,
        )


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_rejects_insecure_cookies_when_deployed(environment: str) -> None:
    with pytest.raises(ValidationError, match="COOKIE_SECURE"):
        Settings(
            _env_file=None,
            database_url=DATABASE_URL,
            environment=environment,
            session_secret_key=PRIVATE_SECRET,
            cookie_secure=False,
        )


def test_accepts_a_secure_staging_configuration() -> None:
    settings = Settings(
        _env_file=None,
        database_url=DATABASE_URL,
        environment="staging",
        session_secret_key=PRIVATE_SECRET,
        cookie_secure=True,
    )

    assert settings.environment == "staging"


@pytest.mark.parametrize("environment", ["development", "test"])
def test_local_environments_accept_the_dev_defaults(environment: str) -> None:
    settings = Settings(_env_file=None, database_url=DATABASE_URL, environment=environment)

    assert settings.session_secret_key == DEV_SESSION_SECRET_KEY
    assert settings.cookie_secure is False


def test_reads_the_deployed_commit_from_render(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RENDER_GIT_COMMIT", "0123abc")

    settings = Settings(_env_file=None, database_url=DATABASE_URL)

    assert settings.git_commit == "0123abc"


def test_git_commit_is_unset_outside_render(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)

    settings = Settings(_env_file=None, database_url=DATABASE_URL)

    assert settings.git_commit is None


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_rejects_recorded_toast_data_when_deployed(environment: str) -> None:
    with pytest.raises(ValidationError, match="TOAST_USE_RECORDED_DATA"):
        Settings(
            _env_file=None,
            database_url=DATABASE_URL,
            environment=environment,
            session_secret_key=PRIVATE_SECRET,
            cookie_secure=True,
            toast_use_recorded_data=True,
        )


def test_recorded_toast_data_is_off_unless_asked_for() -> None:
    assert Settings(_env_file=None, database_url=DATABASE_URL).toast_use_recorded_data is False
    local = Settings(_env_file=None, database_url=DATABASE_URL, toast_use_recorded_data=True)
    assert local.toast_use_recorded_data is True
