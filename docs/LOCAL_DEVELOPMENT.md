# Local development

Use the [README quick start](../README.md#quick-start) for the default SQLite run.
This guide covers configuration, PostgreSQL, native Windows, and alternative
startup methods. Run commands from the repository root unless stated otherwise.

## Environment configuration

The canonical templates are [backend/.env.example](../backend/.env.example) and
[frontend/.env.example](../frontend/.env.example). The root [.env.example](../.env.example)
is a combined reference. Setup creates missing files and preserves existing ones.

Backend settings live in `backend/.env`:

- `DATABASE_URL`: defaults to `sqlite+aiosqlite:///./odte_gex.db`, stored in `backend/odte_gex.db`.
- `DATA_PROVIDER`: `yfinance` by default; use `tradier` with a configured key.
- `TRADIER_API_KEY`: required for Tradier.
- `TRADIER_BASE_URL`: selects the Tradier API environment.
- Other backend settings, including CORS and environment mode, are documented in the template.

Frontend endpoints live in `frontend/.env.local`:

- `NEXT_PUBLIC_API_URL=http://localhost:8000`
- `NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws`

Exported environment variables take precedence over dotenv files. Restart the
relevant service after changing its configuration.

```bash
./scripts/setup_env.sh                   # Preserve and validate existing settings
./scripts/setup_env.sh --sqlite          # Select the SQLite database URL
./scripts/setup_env.sh --postgres-local  # Select the local PostgreSQL preset
./scripts/setup_env.sh --postgres-docker # Select the Docker Compose preset
```

An explicit preset updates only `DATABASE_URL` in `backend/.env`. The bootstrap
validates the database/API/WebSocket URLs and removes an obsolete
`POLYGON_API_KEY` assignment from the root `.env` when present.

## PostgreSQL options

### Docker Compose

Requires Docker and Docker Compose. The preset matches Compose's default
user, password, database, and port. If `POSTGRES_USER`, `POSTGRES_PASSWORD`, or
`POSTGRES_DB` is overridden in the root `.env` or shell, update `backend/.env`
to match it.

```bash
./scripts/setup_env.sh --postgres-docker
docker compose up -d
./scripts/dev.sh
```

The default database endpoint is `localhost:5432`.

### Project-owned local server

On Linux/WSL with the PostgreSQL tools available:

```bash
./scripts/setup_env.sh --postgres-local
./scripts/setup_local_postgres.sh
./scripts/dev.sh
```

This preset uses `127.0.0.1:55432`. See [setup_local_postgres.sh](../scripts/setup_local_postgres.sh)
for the project-owned server setup. The runner ensures that server is started
before applying migrations.

### Existing or shared server

Set `DATABASE_URL` in `backend/.env` to your server's connection string:

```dotenv
DATABASE_URL=postgresql+asyncpg://odte_user:your_password@your_host:5432/odte_gex
```

Then run `./scripts/dev.sh`. The runner waits for the endpoint and applies the
existing migrations. For shared infrastructure, see the
[shared PostgreSQL milestone](PROVIDER_INTEGRATION_PLAN.md#3-p2--roll-out-shared-postgresql-when-teammates-need-shared-history)
and [deployment guide](DEPLOYMENT.md).

## Native Windows PowerShell

With Python 3.12+, Node.js 20+, and pnpm available, run from the repository root:

```powershell
python -m venv backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
pnpm --dir frontend install --frozen-lockfile
if (-not (Test-Path backend\.env)) { Copy-Item backend\.env.example backend\.env }
if (-not (Test-Path frontend\.env.local)) { Copy-Item frontend\.env.example frontend\.env.local }
powershell -ExecutionPolicy Bypass -File .\scripts\start_app.ps1
```

Keep existing environment files when rerunning setup. The launcher uses SQLite
by default and skips PostgreSQL checks in that mode. It runs migrations before
opening the backend and frontend terminals and stops if migration fails.

For local PostgreSQL on native Windows, install and start the server separately,
then configure `DATABASE_URL`. The launcher shows setup guidance if the server
is missing or unreachable. WSL supports the Bash runner and managed local server.

Stop native Windows services with `Ctrl+C` in each terminal or by closing their
windows. `dev.sh` requires POSIX process groups and does not support native
Windows Python, including Python invoked from Git Bash.

## Legacy multi-terminal startup

On Linux/WSL, after installing dependencies and configuring the environment:

```bash
./scripts/start_app.sh
```

Backend and frontend run in separate terminals. The project-owned PostgreSQL
fallback gets a database terminal; SQLite and an external database do not.
The backend terminal uses `uvicorn --reload` and the frontend runs `pnpm dev`.

```bash
./scripts/stop_app.sh
```

The stop script stops the frontend, backend, and project-owned PostgreSQL in that
order, using `pg_ctl` for the database. Stopping only an app terminal can leave
the local database running until it is stopped separately.

## Manual startup

These commands use a POSIX shell on Linux, macOS, or WSL. Complete the quick
start's dependency and environment setup first. For PostgreSQL, start the chosen
server before migrating. Use two terminals, each starting in the repository root.

Backend terminal:

```bash
cd backend
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m uvicorn app.main:app --reload
```

Frontend terminal:

```bash
pnpm --dir frontend dev
```

Open [the dashboard](http://localhost:3000) or [API docs](http://localhost:8000/docs).
Stop each service with `Ctrl+C` in its terminal.

## Development checks

The [README tests](../README.md#tests) cover the deterministic suite and linting.
For backend type checking, from the repository root:

```bash
(cd backend && .venv/bin/python -m mypy app)
```

Run explicitly marked live integration tests separately, with the required
provider access configured:

```bash
(cd backend && .venv/bin/python -m pytest -q -m integration)
```

For the non-gating Greeks timing probe, use the command in
[BENCHMARKS.md](BENCHMARKS.md). Follow [CONTRIBUTING.md](../CONTRIBUTING.md) for
code conventions and contribution checks.
