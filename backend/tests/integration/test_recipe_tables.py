# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""The recipe schema (db/07_recipes.sql) on a real database.

Each test runs in a throwaway database (see ``scratch_engine``).
"""

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import migrate_down, migrate_up


@pytest.fixture
def db(migrated_engine: Engine) -> Iterator[Session]:
    with Session(migrated_engine) as session:
        yield session


def add_restaurant(db: Session) -> uuid.UUID:
    statement = text("INSERT INTO restaurants (name) VALUES ('Mykonos Grill') RETURNING id")
    restaurant_id: uuid.UUID = db.execute(statement).scalar_one()
    return restaurant_id


def add_ingredient(db: Session, restaurant_id: uuid.UUID, kind: str, base_unit: str) -> None:
    db.execute(
        text("""
            INSERT INTO ingredients (restaurant_id, name, kind, base_unit)
            VALUES (:restaurant_id, 'Feta', :kind, :base_unit)
        """),
        {"restaurant_id": restaurant_id, "kind": kind, "base_unit": base_unit},
    )


def test_migration_runs_again_and_undoes(migrated_engine: Engine) -> None:
    migrate_up(migrated_engine)  # a second run changes nothing and does not fail
    migrate_down(migrated_engine)
    migrate_up(migrated_engine)
    with migrated_engine.connect() as connection:
        tables = connection.execute(
            text("SELECT count(*) FROM pg_tables WHERE tablename LIKE 'recipe%'")
        ).scalar_one()
    assert tables == 4


def test_base_unit_must_match_kind(db: Session) -> None:
    restaurant_id = add_restaurant(db)
    with pytest.raises(IntegrityError, match="ck_ingredients_kind_unit"):
        add_ingredient(db, restaurant_id, kind="mass", base_unit="ml")


def test_ingredient_names_are_unique_regardless_of_capitals(db: Session) -> None:
    restaurant_id = add_restaurant(db)
    add_ingredient(db, restaurant_id, kind="mass", base_unit="g")
    with pytest.raises(IntegrityError, match="uq_ingredients_name"):
        db.execute(
            text("""
                INSERT INTO ingredients (restaurant_id, name, kind, base_unit)
                VALUES (:restaurant_id, 'FETA', 'mass', 'g')
            """),
            {"restaurant_id": restaurant_id},
        )
