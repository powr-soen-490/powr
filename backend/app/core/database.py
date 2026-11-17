# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Database engine, request-scoped sessions, connectivity checks and schema scripts."""

import argparse
import logging
from collections.abc import Iterator
from pathlib import Path

from fastapi import Request
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

# Without a timeout, an unresponsive host blocks a request until the OS gives up (often over a
# minute). Five seconds still leaves room for a suspended free-tier database to wake up.
CONNECT_TIMEOUT_SECONDS = 5

# The schema scripts (01_init.sql, 02_auth_tables.sql, ...). Docker runs them in name order
# when it first creates its database; migrate_up does the same for any existing database.
DB_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "db"

# Undo db/02_auth_tables.sql and db/06_pos_sales_import.sql. Kept here instead of in db/,
# because Docker runs every .sql file in that folder.
DROP_AUTH_TABLES = "DROP TABLE IF EXISTS eula_acceptances, invites, restaurant_memberships, users"
DROP_SALES_IMPORT_TABLES = (
    "DROP TABLE IF EXISTS sync_jobs, sales_order_lines, sales_orders, menu_modifiers, menu_items"
)
# Undo db/07_recipes.sql's tables. Its new ingredients columns stay: that table comes from
# 01_init.sql, which down never undoes.
DROP_RECIPE_TABLES = (
    "DROP TABLE IF EXISTS recipe_modifier_lines, recipe_lines, recipe_versions, recipes"
)


def create_session_factory(database_url: str) -> sessionmaker[Session]:
    # pool_pre_ping replaces connections dropped while the free-tier database was suspended.
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        connect_args={"connect_timeout": CONNECT_TIMEOUT_SECONDS},
    )
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db(request: Request) -> Iterator[Session]:
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_factory() as session:
        yield session


def is_database_reachable(session: Session) -> bool:
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("Database connectivity check failed")
        return False
    return True


def migrate_up(engine: Engine) -> None:
    """Runs every script in db/ in name order, in one transaction.

    The scripts only create what is missing, so this is safe to repeat and keeps existing data.
    """
    connection = engine.raw_connection()
    try:
        cursor = connection.cursor()
        for script in sorted(DB_SCRIPTS_DIR.glob("*.sql")):
            # Sent through the driver as-is: SQLAlchemy would read the '%' in the scripts'
            # header comments as parameter placeholders.
            cursor.execute(script.read_text(encoding="utf-8"))
        connection.commit()
    finally:
        connection.close()


def migrate_down(engine: Engine) -> None:
    """Undoes db/02_auth_tables.sql, db/06_pos_sales_import.sql and db/07_recipes.sql: drops
    their tables and everything in them."""
    with engine.begin() as connection:
        connection.execute(text(DROP_RECIPE_TABLES))
        connection.execute(text(DROP_SALES_IMPORT_TABLES))
        connection.execute(text(DROP_AUTH_TABLES))


if __name__ == "__main__":
    # From backend/: python -m app.core.database up   (or down)
    from app.core.config import get_settings

    parser = argparse.ArgumentParser(description="Apply or undo the schema scripts in db/.")
    parser.add_argument("direction", choices=["up", "down"])
    direction = parser.parse_args().direction
    engine = create_engine(str(get_settings().database_url))
    try:
        if direction == "up":
            migrate_up(engine)
        else:
            migrate_down(engine)
    finally:
        engine.dispose()
    print(f"Database migrated {direction}.")
