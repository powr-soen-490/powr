# powr

Ingredient demand forecasting for independent restaurants. powr imports sales from the
restaurant's POS (Toast first), converts menu-item sales into ingredient usage through recipes,
forecasts demand, and recommends supplier orders that the kitchen manager reviews and approves.

## Stack

- Backend: Python 3.12, FastAPI, synchronous SQLAlchemy 2.0, PostgreSQL 16
- Frontend: React + TypeScript (Vite)
- Tooling: Ruff (lint + format), mypy (strict), pytest, Playwright, GitHub Actions

## Repository layout

```
backend/
  app/
    main.py            FastAPI application entry point (uvicorn app.main:app)
    core/              settings, database, logging; shared by all modules
    api/               top-level router and app-wide endpoints (health)
    integrations/      provider-independent contracts with external systems
      pos/             PosAdapter interface and internal POS models; <provider>/ per POS
    modules/           one package per business area
      pos/             POS sync and POS credentials
      forecasting/     demand forecasting and order recommendations
  db/                  legacy SQL init script, to be replaced by Alembic migrations
  tests/               unit/ (no database) and integration/ (real PostgreSQL)
frontend/              React + TypeScript app
scripts/               repository tooling
docker-compose.yml     local PostgreSQL + backend
```

Setup and run instructions are in `README.md`.

## Architecture rules

- Modular monolith: one deployable backend, organised by business area under `app/modules/`.
- Inside a module: `router.py` -> `service.py` -> `repository.py` -> `models.py`. Routers hold no
  business logic or SQL; services never import FastAPI.
- Modules call each other only through services, never another module's repository or models.
- Every restaurant-owned table has a `restaurant_id`, and every query filters by it.
- Raw POS payloads never leave `integrations/pos/<provider>/`; adapters return the internal
  models in `integrations/pos/models.py`.
- Configuration comes from environment variables only. Never commit `.env` or secrets.
- Timestamps are timezone-aware (UTC); money and quantities use `Decimal`/`NUMERIC`, never floats.
- Primary keys are UUIDs.

## Commands (run from `backend/`)

```
pip install -r requirements-dev.txt
ruff check . && ruff format --check .
mypy
pytest
python
```

## Conventions

- Every source file starts with this header (use the language's comment syntax), where the AI
  level is exactly one of `No substantial AI-generated code`, `Below 50% AI-generated`,
  `50% or more AI-generated`:
  ```
  # Copyright 2026 POWR Contributors
  # AI contribution: 50% or more AI-generated
  ```
  Update the AI level when a change shifts the balance. Check with `python scripts/check_headers.py`.
- Code-quality limits (enforced by Ruff): cyclomatic complexity <= 15, <= 50 statements per
  function. Keep files under 500 lines.
- Branches: `<type>/<issue-number>-<short-description>`, e.g. `feat/8-project-structure`.
- Commits: Conventional Commits (`feat(backend): ...`, `fix: ...`); releases depend on it.
- Default branch is `master`; all changes go through a reviewed pull request.
