#!/usr/bin/env bash
#
# dev.sh — single-process local dev runner (SQLite default, no Docker required).
#
# Runs database migrations, then the backend (uvicorn) and the frontend
# (pnpm dev) together as one child process group of this script:
#   - one PID file:  .local-run/dev.pid  (this script's own PID)
#   - one log file:  .local-run/dev.log  (both services, prefixed per line)
#   - Ctrl+C (INT) or TERM stops backend + frontend + their descendants.
#
# Database behavior:
#   - SQLite DATABASE_URL (the default): no DB terminal, no TCP wait.
#     The SQLite file (backend/odte_gex.db) is created on first run.
#   - Postgres on 127.0.0.1/localhost:55432: the project-owned local
#     Postgres is ensured via setup_local_postgres.sh, then we wait for it.
#   - Any other Postgres URL: treated as external (e.g. `docker compose up -d`
#     first); we wait for it to become reachable, then continue.
#
# The multi-terminal launchers (start_app.sh + run_*_dev.sh) remain as legacy
# shims; this script intentionally never opens a terminal window.
#
set -euo pipefail

REPO_ROOT="${ODTE_REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
BACKEND_DIR="$REPO_ROOT/backend"
FRONTEND_DIR="$REPO_ROOT/frontend"
BACKEND_VENV_BIN="${ODTE_BACKEND_VENV_BIN:-$BACKEND_DIR/.venv/bin}"
RUNTIME_DIR="${ODTE_RUNTIME_DIR:-$REPO_ROOT/.local-run}"
LOG_FILE="$RUNTIME_DIR/dev.log"
PID_FILE="$RUNTIME_DIR/dev.pid"
DEFAULT_DATABASE_URL="sqlite+aiosqlite:///./odte_gex.db"
# Seconds to wait for backend /health and frontend HTTP readiness.
# Set ODTE_DEV_SKIP_WAIT=1 to skip readiness gating (used by automated tests).
BACKEND_WAIT_SECS="${ODTE_DEV_BACKEND_WAIT_SECS:-60}"
FRONTEND_WAIT_SECS="${ODTE_DEV_FRONTEND_WAIT_SECS:-120}"

BACKEND_PID=""
FRONTEND_PID=""
SHUTTING_DOWN=0

fail() {
  echo "Error: $*" >&2
  exit 1
}

log() {
  # Log line goes to stdout and, once initialized, to the shared log file.
  echo "[dev] $*"
  if [[ -d "$RUNTIME_DIR" ]]; then
    echo "[dev] $*" >> "$LOG_FILE"
  fi
}

redact_url() {
  # Never print DB credentials: postgresql://user:pass@host -> postgresql://***@host
  printf '%s\n' "$1" | sed -E 's#(://[^/@]*@)#://***@#'
}

require_file() {
  local path="$1"
  [[ -f "$path" ]] || fail "Required file not found: $path"
}

require_command() {
  local command_name="$1"
  command -v "$command_name" >/dev/null 2>&1 || fail "Required command not found: $command_name"
}

is_sqlite_url() {
  [[ "$1" == sqlite* ]]
}

read_database_url() {
  local env_file="$BACKEND_DIR/.env"
  local database_url=""

  if [[ -f "$env_file" ]]; then
    database_url="$(awk -F= '/^[[:space:]]*DATABASE_URL=/{sub(/^[^=]*=/, ""); print; exit}' "$env_file")"
  fi

  if [[ -z "$database_url" ]]; then
    database_url="$DEFAULT_DATABASE_URL"
  fi

  printf '%s\n' "$database_url"
}

parse_database_endpoint() {
  local database_url="$1"

  python3 - "$database_url" <<'PY'
import sys
from urllib.parse import urlparse

database_url = sys.argv[1].replace("postgresql+asyncpg://", "postgresql://", 1)
parsed = urlparse(database_url)
host = parsed.hostname or "127.0.0.1"
port = parsed.port or 5432
print(host)
print(port)
PY
}

determine_db_mode() {
  local host="$1"
  local port="$2"

  if [[ "$host" =~ ^(127\.0\.0\.1|localhost)$ && "$port" == "55432" ]]; then
    echo "local"
    return
  fi

  echo "external"
}

wait_for_tcp() {
  local host="$1"
  local port="$2"
  local timeout_secs="${3:-60}"

  python3 - "$host" "$port" "$timeout_secs" <<'PY'
import socket
import sys
import time

host = sys.argv[1]
port = int(sys.argv[2])
timeout_secs = int(sys.argv[3])

deadline = time.time() + timeout_secs
while time.time() < deadline:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        try:
            sock.connect((host, port))
        except OSError:
            time.sleep(1)
            continue
        else:
            sys.exit(0)

sys.exit(1)
PY
}

wait_for_http_ok() {
  local url="$1"
  local timeout_secs="$2"

  python3 - "$url" "$timeout_secs" <<'PY'
import sys
import time
import urllib.request

url = sys.argv[1]
timeout_secs = int(sys.argv[2])

deadline = time.time() + timeout_secs
while time.time() < deadline:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            if response.status == 200:
                sys.exit(0)
    except Exception:
        pass
    time.sleep(2)

sys.exit(1)
PY
}

prefix_stream() {
  # Prefix every stdin line with the service tag (line-buffered).
  local prefix="$1"
  while IFS= read -r line || [[ -n "$line" ]]; do
    printf '%s %s\n' "$prefix" "$line"
  done
}

kill_tree() {
  # SIGTERM a process and all of its descendants (best effort, no orphans).
  local root_pid="$1"
  local child

  if ! kill -0 "$root_pid" >/dev/null 2>&1; then
    return 0
  fi

  if command -v pgrep >/dev/null 2>&1; then
    while read -r child; do
      if [[ -n "$child" ]]; then
        kill_tree "$child"
      fi
    done < <(pgrep -P "$root_pid" 2>/dev/null || true)
  fi

  kill -TERM "$root_pid" >/dev/null 2>&1 || true
}

shutdown() {
  # Optional first arg: process exit code (default 0).
  local exit_code="${1:-0}"
  if [[ "$SHUTTING_DOWN" -eq 1 ]]; then
    return 0
  fi
  SHUTTING_DOWN=1
  trap - INT TERM

  log "shutting down..."

  if [[ -n "$BACKEND_PID" ]]; then
    kill_tree "$BACKEND_PID"
  fi
  if [[ -n "$FRONTEND_PID" ]]; then
    kill_tree "$FRONTEND_PID"
  fi

  # Brief graceful window, then escalate any stragglers to SIGKILL.
  sleep 3
  for pid in $BACKEND_PID $FRONTEND_PID; do
    if [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1; then
      kill -KILL "$pid" >/dev/null 2>&1 || true
      if command -v pkill >/dev/null 2>&1; then
        pkill -KILL -P "$pid" >/dev/null 2>&1 || true
      fi
    fi
  done

  wait "$BACKEND_PID" 2>/dev/null || true
  wait "$FRONTEND_PID" 2>/dev/null || true
  rm -f "$PID_FILE"
  log "stopped."
  exit "$exit_code"
}

require_command python3
require_command pnpm
require_file "$BACKEND_DIR/.env"
require_file "$FRONTEND_DIR/package.json"

venv_has_module() {
  local module="$1"
  [[ -x "$BACKEND_VENV_BIN/python" ]] \
    && "$BACKEND_VENV_BIN/python" -c "import $module" >/dev/null 2>&1
}

if [[ -x "$BACKEND_VENV_BIN/alembic" ]] && venv_has_module "alembic"; then
  ALEMBIC_BIN="$BACKEND_VENV_BIN/alembic"
elif command -v alembic >/dev/null 2>&1; then
  if [[ -x "$BACKEND_VENV_BIN/alembic" ]]; then
    echo "Warning: backend venv looks broken (cannot import alembic); falling back to PATH: $(command -v alembic)" >&2
  fi
  ALEMBIC_BIN="$(command -v alembic)"
else
  fail "alembic not found (looked in $BACKEND_VENV_BIN and on PATH). Create backend/.venv or install backend/requirements.txt."
fi

if [[ -x "$BACKEND_VENV_BIN/uvicorn" ]] && venv_has_module "fastapi"; then
  UVICORN_BIN="$BACKEND_VENV_BIN/uvicorn"
elif command -v uvicorn >/dev/null 2>&1; then
  if [[ -x "$BACKEND_VENV_BIN/uvicorn" ]]; then
    echo "Warning: backend venv looks broken (cannot import fastapi); falling back to PATH: $(command -v uvicorn)" >&2
  fi
  UVICORN_BIN="$(command -v uvicorn)"
else
  fail "uvicorn not found (looked in $BACKEND_VENV_BIN and on PATH). Create backend/.venv or install backend/requirements.txt."
fi

mkdir -p "$RUNTIME_DIR"

if [[ -f "$PID_FILE" ]]; then
  existing_pid="$(<"$PID_FILE")"
  if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" >/dev/null 2>&1; then
    fail "dev runner already running (PID $existing_pid from $PID_FILE). Stop it first (Ctrl+C in its terminal)."
  fi
  rm -f "$PID_FILE"
fi

printf '%s\n' "$$" > "$PID_FILE"
: > "$LOG_FILE"

trap 'shutdown 130' INT
trap 'shutdown 143' TERM

DATABASE_URL_VALUE="$(read_database_url)"
if is_sqlite_url "$DATABASE_URL_VALUE"; then
  DB_MODE="sqlite"
  log "SQLite database configured ($(redact_url "$DATABASE_URL_VALUE")). No DB terminal needed."
  log "SQLite file lives at backend/odte_gex.db (created on first run)."
else
  mapfile -t DB_ENDPOINT < <(parse_database_endpoint "$DATABASE_URL_VALUE")
  DB_HOST="${DB_ENDPOINT[0]}"
  DB_PORT="${DB_ENDPOINT[1]}"
  DB_MODE="$(determine_db_mode "$DB_HOST" "$DB_PORT")"

  if [[ "$DB_MODE" == "local" ]]; then
    log "Local Postgres configured. Ensuring project-owned server is up..."
    "$REPO_ROOT/scripts/setup_local_postgres.sh"
  else
    log "External Postgres configured at $DB_HOST:$DB_PORT. Expecting it to be reachable (e.g. via 'docker compose up -d')."
  fi

  log "Waiting for database at $DB_HOST:$DB_PORT ..."
  wait_for_tcp "$DB_HOST" "$DB_PORT" 60 || fail "Database did not become reachable at $DB_HOST:$DB_PORT."
fi

log "Running backend migrations..."
(
  cd "$BACKEND_DIR"
  "$ALEMBIC_BIN" upgrade head
)

log "Starting backend (uvicorn) and frontend (pnpm dev) as one process group..."

cd "$BACKEND_DIR"
"$UVICORN_BIN" app.main:app --reload \
  > >(prefix_stream "[backend]" >> "$LOG_FILE") 2>&1 &
BACKEND_PID="$!"

cd "$FRONTEND_DIR"
pnpm dev \
  > >(prefix_stream "[frontend]" >> "$LOG_FILE") 2>&1 &
FRONTEND_PID="$!"

log "backend PID $BACKEND_PID, frontend PID $FRONTEND_PID."
log "Logs: $LOG_FILE (lines prefixed [backend]/[frontend]). Stop with Ctrl+C."

if [[ "${ODTE_DEV_SKIP_WAIT:-0}" != "1" ]]; then
  log "Waiting for backend http://localhost:8000/health ..."
  if wait_for_http_ok "http://localhost:8000/health" "$BACKEND_WAIT_SECS"; then
    log "Backend is up: http://localhost:8000 (docs: http://localhost:8000/docs)"
  else
    log "Backend did not answer /health within ${BACKEND_WAIT_SECS}s — check $LOG_FILE."
  fi

  log "Waiting for frontend http://localhost:3000 ..."
  if wait_for_http_ok "http://localhost:3000/" "$FRONTEND_WAIT_SECS"; then
    log "Frontend is up: http://localhost:3000"
  else
    log "Frontend did not answer within ${FRONTEND_WAIT_SECS}s — check $LOG_FILE."
  fi
fi

# If either service exits on its own, stop the other and exit non-zero.
set +e
wait -n "$BACKEND_PID" "$FRONTEND_PID"
service_status="$?"
set -e
log "A service exited (status $service_status); stopping the other."
shutdown "$service_status"
