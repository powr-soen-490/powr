# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Shared pytest fixtures."""

import os
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, make_url, text
from sqlalchemy.exc import ProgrammingError

# Read before the default below is applied: only a DATABASE_URL provided by the caller
# (CI, or a developer exporting it) points at a real database for integration tests.
INTEGRATION_DATABASE_URL = os.environ.get("DATABASE_URL")

# app.main builds the module-level app at import time, which requires a database URL.
# Creating the engine does not connect, so a placeholder is enough for unit tests.
UNIT_TEST_DATABASE_URL = "postgresql://powr:powr@localhost:5432/powr_test"
os.environ.setdefault("DATABASE_URL", UNIT_TEST_DATABASE_URL)

from app.core.config import Settings  # noqa: E402
from app.core.database import migrate_up  # noqa: E402
from app.main import create_app  # noqa: E402

# Meets the password policy; used by sign_up_owner.
TEST_PASSWORD = "Str0ng!Password"


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, database_url=UNIT_TEST_DATABASE_URL)


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def integration_database_url() -> str:
    if INTEGRATION_DATABASE_URL is None:
        pytest.skip("DATABASE_URL is not set; integration tests need a running PostgreSQL")
    return INTEGRATION_DATABASE_URL


@pytest.fixture
def scratch_engine(integration_database_url: str) -> Iterator[Engine]:
    """An empty throwaway database on the DATABASE_URL server, dropped after the test.

    Tests can create, delete and migrate freely without touching a developer's own data.
    """
    name = f"powr_test_{uuid.uuid4().hex[:12]}"
    server = create_engine(integration_database_url, isolation_level="AUTOCOMMIT")
    try:
        with server.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
    except ProgrammingError as error:
        server.dispose()
        if isinstance(error.orig, psycopg.errors.InsufficientPrivilege):
            message = "the DATABASE_URL user cannot create a scratch database"
            # A skip would let CI pass without running these tests.
            if os.environ.get("CI"):
                pytest.fail(message)
            pytest.skip(message)
        raise
    scratch = create_engine(make_url(integration_database_url).set(database=name))
    try:
        yield scratch
    finally:
        scratch.dispose()
        with server.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        server.dispose()


@pytest.fixture
def migrated_engine(scratch_engine: Engine) -> Engine:
    migrate_up(scratch_engine)
    return scratch_engine


@pytest.fixture
def api_app(migrated_engine: Engine) -> FastAPI:
    url = migrated_engine.url.render_as_string(hide_password=False)
    return create_app(Settings(_env_file=None, database_url=url))


@pytest.fixture
def make_client(api_app: FastAPI) -> Iterator[Callable[[], TestClient]]:
    """Each client keeps its own cookies, so each one is a separate browser session."""
    clients: list[TestClient] = []

    def make() -> TestClient:
        client = TestClient(api_app)
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.close()


@pytest.fixture
def sign_up_owner() -> Callable[[TestClient, str], dict[str, Any]]:
    """Signs up a new restaurant owner through the API; the client keeps the session cookie."""

    def sign_up(client: TestClient, email: str) -> dict[str, Any]:
        response = client.post(
            "/api/auth/signup",
            json={
                "restaurant_name": f"Restaurant of {email}",
                "email": email,
                "password": TEST_PASSWORD,
                "eula_accepted": True,
            },
        )
        assert response.status_code == 201, response.text
        body: dict[str, Any] = response.json()
        return body

    return sign_up
