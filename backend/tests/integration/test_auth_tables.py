# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Integration tests for issue #39: db/02_auth_tables.sql, migrated up and down.

Each test runs in a throwaway database on the DATABASE_URL server, so migrating down never
touches a developer's own data. Skipped when that user cannot create databases.
"""

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, Engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.core.database import migrate_down, migrate_up

AUTH_TABLES = {"users", "restaurant_memberships", "invites", "eula_acceptances"}


@pytest.fixture
def engine(scratch_engine: Engine) -> Engine:
    return scratch_engine


@pytest.fixture
def migrated(engine: Engine) -> Iterator[Connection]:
    migrate_up(engine)
    with engine.connect() as connection:
        yield connection


def table_names(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names())


def add_user(connection: Connection, email: str) -> uuid.UUID:
    statement = text("INSERT INTO users (email, password_hash) VALUES (:email, 'x') RETURNING id")
    user_id: uuid.UUID = connection.execute(statement, {"email": email}).scalar_one()
    return user_id


def add_membership(
    connection: Connection, user_id: uuid.UUID, restaurant_id: uuid.UUID, role: str
) -> None:
    connection.execute(
        text(
            "INSERT INTO restaurant_memberships (user_id, restaurant_id, role) "
            "VALUES (:user_id, :restaurant_id, :role)"
        ),
        {"user_id": user_id, "restaurant_id": restaurant_id, "role": role},
    )


def test_migration_runs_up_and_down_cleanly(engine: Engine) -> None:
    migrate_up(engine)
    migrate_up(engine)  # running it twice changes nothing
    assert table_names(engine) >= AUTH_TABLES | {"restaurants"}

    migrate_down(engine)
    assert table_names(engine).isdisjoint(AUTH_TABLES)
    assert "restaurants" in table_names(engine)  # down only removes this issue's tables

    migrate_up(engine)
    assert table_names(engine) >= AUTH_TABLES


def test_email_is_unique(migrated: Connection) -> None:
    add_user(migrated, "john@example.com")
    with pytest.raises(IntegrityError, match="uq_users_email_lower"):
        add_user(migrated, "john@example.com")


@pytest.mark.parametrize("email", ["John@example.com", "john@example.com ", " john@example.com"])
def test_email_must_be_lowercase_without_spaces(migrated: Connection, email: str) -> None:
    with pytest.raises(IntegrityError, match="users_email_check"):
        add_user(migrated, email)


def test_membership_needs_an_existing_restaurant(migrated: Connection) -> None:
    user_id = add_user(migrated, "john@example.com")
    with pytest.raises(IntegrityError, match="restaurant_memberships_restaurant_id_fkey"):
        add_membership(migrated, user_id, uuid.uuid4(), "owner")


def test_role_must_be_owner_or_kitchen_manager(migrated: Connection) -> None:
    user_id = add_user(migrated, "john@example.com")
    restaurant_id = migrated.execute(
        text("INSERT INTO restaurants (name) VALUES ('Mykonos Grill') RETURNING id")
    ).scalar_one()
    with pytest.raises(IntegrityError, match="restaurant_memberships_role_check"):
        add_membership(migrated, user_id, restaurant_id, "admin")
