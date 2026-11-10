# POWR

[![ci](https://github.com/powr-soen-490/powr/actions/workflows/ci.yml/badge.svg)](https://github.com/powr-soen-490/powr/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/powr-soen-490/powr/branch/master/graph/badge.svg)](https://codecov.io/gh/powr-soen-490/powr)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=powr-soen-490_powr&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=powr-soen-490_powr)

Stack: React (TypeScript) frontend, FastAPI (Python) backend, PostgreSQL database.
Architecture rules are in [`CLAUDE.md`](CLAUDE.md), and the AI declaration policy in
[`AGENTS.md`](AGENTS.md).

## Getting started

Commands assume macOS or Linux; Windows differences are noted.

### 1. Prerequisites

| Tool | Version | Check with | Needed for |
|---|---|---|---|
| Git | any | `git --version` | everything |
| Python | 3.12 | `python3.12 --version` | running the backend without Docker, tests, linting |
| Node.js | 22 | `node --version` | running the frontend without Docker, frontend and e2e tests |
| Docker Desktop | any recent | `docker --version` | running with Docker |
| PostgreSQL | 16 | `psql --version` | running the backend without Docker |

On macOS with Homebrew: `brew install python@3.12 postgresql@16`. Docker Desktop is available
from [docker.com](https://www.docker.com/products/docker-desktop/).

### 2. Get the code and create your `.env`

```bash
git clone git@github.com:gabrielshufelt/powr.git
cd powr
cp .env.example .env
```

`.env` holds your local settings and is never committed. The defaults work as-is; every
variable is explained in [`.env.example`](.env.example).

### 3. Run the backend

Choose one of the two options.

#### Option A: with Docker

From the repository root:

```bash
docker compose up --build
```

This starts PostgreSQL on port 5432, the backend on port 8000 and the frontend on port 5173,
reloading when you edit code. Stop with `Ctrl+C`, then `docker compose down`. To reset the
database completely (deletes all local data), run `docker compose down -v`. After changing
frontend dependencies, run `docker compose up --build -V` so the container reinstalls them.

#### Option B: directly on your machine

This is also the setup needed to run tests, linting and type checks locally.

1. Create a virtual environment and install dependencies:

   ```bash
   cd backend
   python3.12 -m venv .venv
   source .venv/bin/activate          # Windows: .venv\Scripts\activate
   pip install -r requirements-dev.txt
   ```

   Your prompt now starts with `(.venv)`. **Run `source .venv/bin/activate` again in every
   new terminal** before using `uvicorn`, `pytest`, `ruff` or `mypy`.

2. Start PostgreSQL (`brew services start postgresql@16` on macOS), then create the user and
   database that `.env` expects:

   ```bash
   psql -h localhost -d postgres -c "CREATE USER powr_user WITH PASSWORD 'powr_password' CREATEDB;"
   psql -h localhost -d postgres -c "CREATE DATABASE powr_dev OWNER powr_user;"
   ```

   `CREATEDB` lets the tests create their own databases: without it the integration tests are
   skipped and the end-to-end tests cannot start.

   If `psql` asks for a password you don't know, see [Troubleshooting](#troubleshooting).

3. Create the app's tables in `powr_dev`. Run this from `backend/`, with the virtual
   environment active:

   ```bash
   python -m app.core.database up
   ```

   It prints `Database migrated up.` Run it again whenever you pull a new file in
   `backend/db/`; it only adds what is missing and keeps your data.

4. Start the backend from `backend/`, with the virtual environment active:

   ```bash
   uvicorn app.main:app --reload
   ```

   It reads its settings from the `.env` file in the repository root.

5. In another terminal, start the frontend:

   ```bash
   cd frontend
   npm ci
   npm run dev
   ```

### 4. Verify it works

With the backend running, open a second terminal:

```bash
curl http://localhost:8000/health
```

The expected response is `{"status": "ok", "database": "ok"}`. If you get
`{"status": "degraded", "database": "unavailable"}` (HTTP 503), the backend is running but
cannot reach PostgreSQL; see [Troubleshooting](#troubleshooting).

Interactive API documentation is at <http://localhost:8000/docs>, and the frontend is at
<http://localhost:5173>.

### POS credential encryption

POS client secrets and access tokens are stored using AES-256-GCM. Set
`POS_CREDENTIALS_ENCRYPTION_KEY` in the root `.env` (or the deployment environment) to a
base64-encoded, randomly generated 32-byte key. There is no default key: secret reads and
writes fail if the key is missing. Other endpoints and the metadata-only list still work.

Generate a key, then save its output as `POS_CREDENTIALS_ENCRYPTION_KEY` in `.env`:

```bash
python -c "import base64, secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

Keep the key private and persistent across restarts, and use the same key for every backend
instance sharing a database. Replacing it makes existing ciphertext unreadable; retain the
key securely with your database backups. Never commit a real key.


POST and PATCH credential requests accept optional `access_token` and `expires_at` fields.
On PATCH, an omitted or null token/expiry preserves its current value. Secrets are decrypted
only for server-side integrations; GET responses continue to exclude secrets and tokens.

### E2E Tests
To run the end-to-end tests, from the root directory (the first three commands are needed once):
```bash
npm ci
npm ci --prefix frontend
npx playwright install --with-deps chromium
npm run test:e2e
```
Before running them, start PostgreSQL (`docker compose up`, or your local PostgreSQL) and
activate `backend/.venv` in the same terminal; Docker users need it too (see
[Backend Tests](#backend-tests-and-code-quality)).

Playwright starts its own frontend (<http://localhost:5174>) and backend
(<http://localhost:8001>), separate from the ones you run by hand. That backend uses its own
database, `powr_dev_e2e`, which is wiped and recreated at the start of every run, so tests always
start from the same empty state and never touch your `powr_dev` data. Creating it needs the
`CREATEDB` permission (see [Option B](#option-b-directly-on-your-machine); Docker's user already
has it).

### Frontend Tests and code quality
Run from `frontend/` after `npm ci`. CI runs the same checks.

| Command | What it does |
|---|---|
| `npm test` | Runs the unit tests |
| `npm run lint` | Lints with ESLint |
| `npx tsc -b` | Type checks |

### Backend Tests and code quality

Run from `backend/` with the virtual environment active. CI runs the same checks, so a pull
request passes CI if they pass locally.

Tests run on your machine even if you use Docker: the Docker image does not include the test
tools. So create the virtual environment once (step 1 of
[Option B](#option-b-directly-on-your-machine)); with Docker, that is the only Option B step you
need.

| Command | What it does |
|---|---|
| `pytest` | Runs all tests |
| `ruff check .` | Lints for bugs, unused code, import order and complexity limits |
| `ruff format --check .` | Checks formatting (`ruff format .` fixes it) |
| `mypy` | Checks type hints in strict mode |
| `python ../scripts/check_headers.py` | Checks the Source-File AI Declaration of every applicable file (see [`AGENTS.md`](AGENTS.md)) |

Tests are split into `tests/unit/` (no database needed) and `tests/integration/` (real
PostgreSQL). Each integration test creates its own empty database and deletes it afterwards,
so your `powr_dev` data is never touched. They are **skipped** unless `DATABASE_URL` is set in
your shell and its user has `CREATEDB` (Docker's user does; for Option B, see step 2). With
Docker, keep `docker compose up` running so the database is reachable on `localhost:5432`:

```bash
DATABASE_URL=postgresql://powr_user:powr_password@localhost:5432/powr_dev pytest
```

### Logging

Logging is configured once at startup in `backend/app/core/logging_config.py`. In any module,
create a logger named after the module and use it instead of `print`:

```python
import logging

logger = logging.getLogger(__name__)

logger.info("Imported %d orders for restaurant %s", count, restaurant_id)
```

- Pick the method that matches how important the message is:

  | Method | Use it for |
  |---|---|
  | `logger.debug(...)` | Detail that only helps while developing or debugging |
  | `logger.info(...)` | Normal events worth recording, e.g. a sync finished |
  | `logger.warning(...)` | Something unexpected that the code handled |
  | `logger.error(...)` | A failure; inside an `except` block, use `logger.exception(...)` to include the traceback |

- `LOG_LEVEL` in `.env` controls which messages are printed, without changing any code. Each
  setting prints its own level and everything more important (`DEBUG` < `INFO` < `WARNING` <
  `ERROR`):

  | `LOG_LEVEL` | Printed |
  |---|---|
  | `DEBUG` | debug, info, warning and error messages |
  | `INFO` (default) | info, warning and error messages; debug messages are hidden |
  | `WARNING` | warning and error messages |
  | `ERROR` | error messages only |

  For example, set `LOG_LEVEL=DEBUG` while tracking down a bug to see every detail, then
  restart the backend for the change to take effect.
- **Never log secrets**: passwords, API keys, OAuth tokens or `DATABASE_URL`. Customer
  personal data must not be logged either.

### Feature flags

POWR uses [Flagsmith](https://www.flagsmith.com/) for feature flags in both the React
frontend and FastAPI backend. Create separate Flagsmith environments for development,
staging, and production so each deployment uses its own keys and flag values.

Create these Boolean feature flags in the Flagsmith project, then set their values in each
environment:

| Flag | Page |
|---|---|
| `page_home` | Home |
| `page_recommended_orders` | Recommended Orders |
| `page_forecast` | Forecast |
| `page_menu_mapping` | Menu Mapping |
| `page_inventory` | Inventory & Vendors |
| `page_settings` | Settings |

Keep unfinished pages **off in the Staging environment**. The frontend removes disabled
pages from the sidebar and prevents dashboard links from opening them. Pages default to
off in production if no client-side key is configured; the local frontend defaults them
on in development when no key is present. A missing or unavailable backend flag service
fails closed: guarded endpoints return `503`, and disabled features return `404`.

Add the keys for the matching Flagsmith environment to the root `.env` file:

```dotenv
# Server-side SDK key; keep secret and never expose it to Vite.
FLAGSMITH_SERVER_SIDE_KEY=your-server-side-environment-key
# Client-side environment key; this is public and is embedded in the frontend.
FLAGSMITH_ENVIRONMENT_KEY=your-client-side-environment-key
```

`docker compose` passes both keys to their respective apps. Vite reads the root `.env`
when run directly from `frontend/`; for a deployed frontend, configure
`FLAGSMITH_ENVIRONMENT_KEY` (and optionally `VITE_FLAGSMITH_API_URL`) at build time.
The Flagsmith client key is public; do not put the server-side key in Vercel.
The backend accepts `FLAGSMITH_API_URL` to use a self-hosted Flagsmith API. The client
environment key is public; do not use the backend server-side key in frontend settings.

The app already uses `page_*` flags to control its pages. For a new frontend component,
use the Flagsmith React SDK:

```tsx
const flags = useFlags(['page_inventory'])
if (!flags.page_inventory?.enabled) return null
```

For backend endpoints, apply the shared route dependency so disabled pages cannot reach
their API:

```python
@router.get("/inventory", dependencies=[Depends(require_feature("page_inventory"))])
def get_inventory() -> InventoryResponse:
    ...
```

Import `useFlags` from `@flagsmith/flagsmith/react` and `require_feature` from
`app.core.feature_flags`. Keep frontend and backend flag names aligned with the Flagsmith
environment, and turn on a staging flag only after its page and API are ready to demo.

### Project layout

```
backend/
├── app/
│   ├── main.py            Application entry point (create_app factory)
│   ├── core/              Settings, database sessions, logging
│   ├── api/               App-wide endpoints such as /health
│   └── modules/           Business features, one package each (pos, forecasting, ...)
├── db/01_init.sql         Initial schema, applied by Docker on first database start
├── tests/                 unit/ and integration/ tests
├── requirements.txt       Runtime dependencies (pinned)
├── requirements-dev.txt   Runtime + test and lint tools
└── pyproject.toml         Ruff and mypy configuration
frontend/                  React + TypeScript app
e2e/                       Playwright end-to-end tests
scripts/check_headers.py   Source-File AI Declaration check
scripts/report_vulnerabilities.py   Dependency scan; opens issues on its daily run
docker-compose.yml         Local PostgreSQL + backend + frontend
```

### Troubleshooting

**`command not found: uvicorn` (or `pytest`, `ruff`, `mypy`)**
The virtual environment is not active. From `backend/`, run `source .venv/bin/activate`. If
`.venv` does not exist yet, follow Option B, step 1.

**`/health` returns 503 with `"database": "unavailable"`**
PostgreSQL is not reachable with the credentials in `DATABASE_URL`. The backend terminal logs
the exact reason. Check that PostgreSQL is running (`pg_isready -h localhost`) and that the
user and database from Option B, step 2 exist.

**`psql` asks for a password you don't know (Option B, step 2)**

By default `psql` logs in with your computer's username. Some PostgreSQL installers (such as
the official EnterpriseDB one) only create a user named `postgres`, protected by the password
chosen during installation.

1. **If you remember that password**, add `-U postgres` to the commands and enter it when
   asked:

   ```bash
   psql -h localhost -U postgres -d postgres -c "CREATE USER powr_user WITH PASSWORD 'powr_password' CREATEDB;"
   psql -h localhost -U postgres -d postgres -c "CREATE DATABASE powr_dev OWNER powr_user;"
   ```

2. **If you don't remember it**, create a separate PostgreSQL just for powr on port 5433. This
   needs Homebrew's PostgreSQL (`brew install postgresql@16`) and leaves your existing
   installation untouched.

   1. Set up the database folder (one time only):

      ```bash
      export LC_ALL=en_US.UTF-8
      PG="$(brew --prefix postgresql@16)/bin"
      $PG/initdb -D ~/.local/share/powr-postgres -U postgres --auth-local=trust --auth-host=scram-sha-256
      ```

   2. Start it:

      ```bash
      $PG/pg_ctl -D ~/.local/share/powr-postgres -o "-p 5433" -l ~/.local/share/powr-postgres/server.log start
      ```

   3. Create the powr user and database (no password needed here):

      ```bash
      $PG/psql -p 5433 -U postgres -d postgres -c "CREATE USER powr_user WITH PASSWORD 'powr_password' CREATEDB;"
      $PG/psql -p 5433 -U postgres -d postgres -c "CREATE DATABASE powr_dev OWNER powr_user;"
      ```

   4. In your `.env`, change the port in `DATABASE_URL` from `5432` to `5433`:

      ```
      DATABASE_URL=postgresql://powr_user:powr_password@localhost:5433/powr_dev
      ```

   5. Continue with Option B, step 3.

   This PostgreSQL does not start automatically after a reboot. Start it again with step 2
   (in a new terminal, run the `export` and `PG=` lines from step 1 first), and stop it with
   `$PG/pg_ctl -D ~/.local/share/powr-postgres stop`.

**`ValidationError` mentioning `database_url` on startup**
`DATABASE_URL` is missing or not a PostgreSQL URL. Check that `.env` exists in the repository
root (step 2) and that the value starts with `postgresql://`.

**Docker: `port is already allocated` for 5432**
Another PostgreSQL is already running on your machine. Either stop it
(`brew services stop postgresql@16`), or set `POSTGRES_PORT=5433` in `.env` and change the
port in `DATABASE_URL` to `5433`.

**Docker: schema changes in `db/01_init.sql` are not applied**
That script only runs when the database is first created. Run `docker compose down -v` to
reset the database, then `docker compose up` again.

## CI/CD pipeline

### `ci` workflow ([ci.yml](.github/workflows/ci.yml))

Runs on every pull request and every push to `master`. A failing job blocks merging.

| Job | What it does |
|---|---|
| `lint` | Backend: Ruff (lint and format), mypy, and the Source-File AI Declaration check. Frontend: ESLint and type check |
| `frontend-tests` | Frontend unit tests (Vitest) |
| `backend-tests` | Backend unit and integration tests (pytest) with a PostgreSQL service |

npm and pip dependencies are cached.

### `Playwright Tests` workflow ([playwright.yml](.github/workflows/playwright.yml))

Runs the end-to-end tests on every pull request and every push to `master`. It starts an empty
PostgreSQL, then Playwright starts the backend and frontend exactly as it does locally.

### `release` workflow ([release.yml](.github/workflows/release.yml))

On every push to `master`, [release-please](https://github.com/googleapis/release-please) reads the
[Conventional Commits](https://www.conventionalcommits.org/) since the last release and keeps a release PR
up to date with the new version (semantic versioning) and `CHANGELOG.md`. Merging that PR tags the commit
and publishes the GitHub Release.

`fix:` bumps the patch version, `feat:` the minor, and `feat!:` or `BREAKING CHANGE:` the major.

### `deploy-staging` workflow ([deploy-staging.yml](.github/workflows/deploy-staging.yml))

Runs after `ci` passes on `master`. Waits until the staging backend's `/health` reports the merged commit,
smoke-tests the backend and frontend, and records the deployment in the matching GitHub Release.

### `dependency-scan` workflow ([dependency-scan.yml](.github/workflows/dependency-scan.yml))

Checks dependencies for known vulnerabilities with `pip-audit` (`backend/requirements-dev.txt`, including
transitive packages) and `npm audit` (`frontend/` and the repository root, shown as `frontend` and `e2e`).
Docker base images and GitHub Actions versions are not covered.

The `scan` job does the following:

| Runs on | What it does |
|---|---|
| Every pull request | Reports findings only. The check stays green, so it never blocks merging; keep it out of the required checks |
| Daily at 09:00 UTC, or started from the Actions tab | Reports findings and opens or updates GitHub issues. Green when it runs, whatever it finds; fails only if a scan cannot run |

| Severity | PR warning | Job summary | GitHub issue |
|---|---|---|---|
| High, critical | Yes | Yes | Yes |
| Low, moderate | No | Yes | No |
| Unknown (Python advisory with no severity on [OSV.dev](https://osv.dev)) | No | Yes | No |

**Issues.** Each vulnerable package gets one issue per scan, titled `[deps] <scope>: <package>` and labelled
`dependency-scan`. Later runs update the open issue instead of creating another, so keep its title and
label unchanged. Nothing is closed automatically and no pull requests are opened: put `Closes #<issue>` in
the pull request that fixes it. An issue closed while the package is still vulnerable is opened again on
the next run.

**Accepting a risk.** Add the Python advisory to `IGNORED_PIP_VULNS` in
[scripts/report_vulnerabilities.py](scripts/report_vulnerabilities.py). npm findings have no ignore list, so
they need a fix or an npm `overrides` entry.

**Changing the threshold.** Set `MIN_SEVERITY` in the same script.

To scan locally without creating issues, run this from the repository root (needs npm):

```
pip install pip-audit
python scripts/report_vulnerabilities.py
```

## Deployment

Every merge to `master` deploys to staging:

| Component | Host | URL |
|---|---|---|
| Frontend | Vercel | https://powr-rho.vercel.app |
| Backend | Render | https://powr-backend-staging.onrender.com |
| Database | Neon | connection string set only in Render |

Render deploys the backend once CI passes and applies the database scripts on start. Vercel deploys the
frontend and proxies `/api/*` to Render. The free tiers sleep when idle, so the first request after a pause
can take about a minute.

Run `python scripts/open_staging.py` to open the staging app, `/health` and the Neon console in your browser.

The deployment diagram, secrets, rollback steps and release strategy are in
[docs/deployment.md](docs/deployment.md), also published on the wiki as
[Deployment Plan and Infrastructure](https://github.com/powr-soen-490/powr/wiki/Deployment-Plan-and-Infrastructure).

## Contributing

### Branch naming
Branches for the most part will be created directly from the issue on GitHub, by clicking on "Create a branch" from the development section on the right.

<img width=400 src=https://docs.github.com/assets/cb-28712/mw-1440/images/help/issues/create-a-branch.webp />

This will automatically create a branch and assign it a name like `8-set-up-basic-project-structure`.

Otherwise, follow the conventions listed below:
- small tasks or chores without an issue: `chore/task-title`, for example `chore/update-readme`
- user story branches containing many tasks: `us/issue-number-and-title`, for example `us/34-new-admin-page`

TODO: detail this section once we have versioning system in place.

### Commit messages
No specific commit-message syntax is required. However, make sure that feature and fix commit messages follow these rules:
- describes the actual change rather than using vague wording.
- identifies the affected functionality or component.
- uses a clear action-oriented description.

Obviously, merge commits and automated dependency-update commits are excluded.

### Pull request process
When about to open a pull request, make sure the title includes the issue number in brackets, for example "[#8] Set up basic project structure".
Make sure you assign at least 2 reviewers, ideally people that are in your subteam, or people that have worked on said feature recently.

**Before merging**: Make sure your PR has the following:
- Approval by at least 1 member.
- All checks pass (linter, unit tests, code quality report, etc.).
- Most importantly, your branch is up to date with and REBASED on master.

Finally, do not "squash & merge", always "Merge pull request". This is for better traceability.
