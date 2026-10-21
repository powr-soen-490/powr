# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Starts the backend for the Playwright tests on its own freshly reset database.

From backend/: python -m tests.e2e_server   (playwright.config.ts runs this for you)

The e2e database sits on the same server as DATABASE_URL, named after it with an "_e2e"
suffix (powr_dev -> powr_dev_e2e). It is dropped and recreated on every run, so each run
starts from the same empty state and the development database is never touched.
"""

import os
import sys

import uvicorn
from sqlalchemy import create_engine, make_url, text

from app.core.config import Settings, get_settings
from app.core.database import migrate_up
from app.main import create_app

E2E_PORT = 8001
E2E_SUFFIX = "_e2e"


def reset_e2e_database(database_url: str) -> str:
    """Drops and recreates the e2e database next to database_url, then creates the tables."""
    url = make_url(database_url)
    e2e_url = url.set(database=f"{url.database}{E2E_SUFFIX}")
    server = create_engine(url, isolation_level="AUTOCOMMIT")
    try:
        with server.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{e2e_url.database}" WITH (FORCE)'))
            connection.execute(text(f'CREATE DATABASE "{e2e_url.database}"'))
    finally:
        server.dispose()
    engine = create_engine(e2e_url)
    try:
        migrate_up(engine)
    finally:
        engine.dispose()
    return e2e_url.render_as_string(hide_password=False)


def main() -> None:
    settings = get_settings()
    if settings.environment == "production":
        sys.exit("Refusing to reset a database with ENVIRONMENT=production.")
    e2e_url = reset_e2e_database(str(settings.database_url))
    # Endpoints read settings through get_settings(), so it must see the e2e database too.
    os.environ["DATABASE_URL"] = e2e_url
    get_settings.cache_clear()
    uvicorn.run(create_app(Settings(database_url=e2e_url)), port=E2E_PORT)


if __name__ == "__main__":
    main()
