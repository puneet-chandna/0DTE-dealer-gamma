#!/usr/bin/env bash
#
# setup_env.sh — idempotent local environment bootstrap.
#
# Copies the canonical templates into place ONLY if the target is missing
# (existing files are never overwritten wholesale):
#   backend/.env.example  -> backend/.env
#   frontend/.env.example -> frontend/.env.local
#
# Usage:
#   scripts/setup_env.sh [--sqlite|--postgres-local|--postgres-docker]
#
# The optional flag selects which DATABASE_URL preset is ensured in
# backend/.env (only the DATABASE_URL line is touched, never the whole file).
# With no flag the existing DATABASE_URL is left alone and just validated.
#
#   --sqlite           sqlite+aiosqlite:///./odte_gex.db            (default)
#   --postgres-local   project-owned Postgres on 127.0.0.1:55432
#   --postgres-docker  Docker Compose Postgres on localhost:5432
#
# The script then validates DATABASE_URL, NEXT_PUBLIC_API_URL and
# NEXT_PUBLIC_WS_URL (fail fast with a clear message) and removes the stale
# POLYGON_API_KEY entry from the root .env if present.
#
set -euo pipefail

REPO_ROOT="${ODTE_REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_VENV_BIN="${ODTE_BACKEND_VENV_BIN:-$REPO_ROOT/backend/.venv/bin}"
BACKEND_EXAMPLE="$REPO_ROOT/backend/.env.example"
BACKEND_ENV="$REPO_ROOT/backend/.env"
FRONTEND_EXAMPLE="$REPO_ROOT/frontend/.env.example"
FRONTEND_ENV="$REPO_ROOT/frontend/.env.local"
ROOT_ENV="$REPO_ROOT/.env"

SQLITE_URL="sqlite+aiosqlite:///./odte_gex.db"
POSTGRES_LOCAL_URL="postgresql+asyncpg://odte_user:odte_password@127.0.0.1:55432/odte_gex"
POSTGRES_DOCKER_URL="postgresql+asyncpg://odte_user:odte_password@localhost:5432/odte_gex"

MODE="sqlite"
MODE_EXPLICIT=0
WANT_URL="$SQLITE_URL"

usage() {
  echo "Usage: $0 [--sqlite|--postgres-local|--postgres-docker]" >&2
}

fail() {
  echo "Error: $*" >&2
  exit 1
}

redact_url() {
  # Never print DB credentials: postgresql://user:pass@host -> postgresql://***@host
  printf '%s\n' "$1" | sed -E 's#(://[^/@]*@)#://***@#'
}

read_var() {
  "$ENV_PYTHON" "$SCRIPT_DIR/read_env.py" "$1" "$2"
}

ensure_from_example() {
  local example="$1"
  local target="$2"
  local label="$3"

  [[ -f "$example" ]] || fail "template not found: $example (cannot bootstrap $label)."

  if [[ -f "$target" ]]; then
    echo "$label already exists, leaving it untouched: $target"
  else
    cp "$example" "$target"
    echo "Created $label from template: $target"
  fi
}

set_database_url() {
  "$ENV_PYTHON" - "$1" "$2" <<'PY'
import sys
from dotenv import dotenv_values, set_key

keys = [key for key in dotenv_values(sys.argv[1]) if key.upper() == "DATABASE_URL"]
for key in keys or ["DATABASE_URL"]:
    set_key(sys.argv[1], key, sys.argv[2], quote_mode="never")
PY
}

case "${1:-}" in
  ""|--sqlite)
    MODE="sqlite"
    WANT_URL="$SQLITE_URL"
    if [[ "${1:-}" == "--sqlite" ]]; then
      MODE_EXPLICIT=1
    fi
    ;;
  --postgres-local)
    MODE="postgres-local"
    WANT_URL="$POSTGRES_LOCAL_URL"
    MODE_EXPLICIT=1
    ;;
  --postgres-docker)
    MODE="postgres-docker"
    WANT_URL="$POSTGRES_DOCKER_URL"
    MODE_EXPLICIT=1
    ;;
  -h|--help)
    usage
    exit 0
    ;;
  *)
    usage
    fail "unknown option: $1"
    ;;
esac

if [[ -x "$BACKEND_VENV_BIN/python" ]] && "$BACKEND_VENV_BIN/python" -c 'import dotenv' >/dev/null 2>&1; then
  ENV_PYTHON="$BACKEND_VENV_BIN/python"
elif command -v python3 >/dev/null 2>&1 && python3 -c 'import dotenv' >/dev/null 2>&1; then
  ENV_PYTHON="$(command -v python3)"
else
  fail "python-dotenv is unavailable. Create backend/.venv and install backend/requirements.txt before running setup_env.sh."
fi

ensure_from_example "$BACKEND_EXAMPLE" "$BACKEND_ENV" "backend env"
ensure_from_example "$FRONTEND_EXAMPLE" "$FRONTEND_ENV" "frontend env"

if [[ "$MODE_EXPLICIT" -eq 1 ]]; then
  set_database_url "$BACKEND_ENV" "$WANT_URL"
  echo "Set DATABASE_URL for mode '$MODE' in $BACKEND_ENV"
fi

# --- validation (fail fast with a clear message) ---
DATABASE_URL_VALUE="$(read_var "$BACKEND_ENV" "DATABASE_URL")"
API_URL_VALUE="$(read_var "$FRONTEND_ENV" "NEXT_PUBLIC_API_URL")"
WS_URL_VALUE="$(read_var "$FRONTEND_ENV" "NEXT_PUBLIC_WS_URL")"

# --- stale provider key cleanup (root .env only, never touch app env files) ---
if [[ -f "$ROOT_ENV" ]]; then
  "$ENV_PYTHON" - "$ROOT_ENV" <<'PY'
import sys
from dotenv import dotenv_values, unset_key

if "POLYGON_API_KEY" in dotenv_values(sys.argv[1]):
    unset_key(sys.argv[1], "POLYGON_API_KEY")
    print(f"Removed stale POLYGON_API_KEY from {sys.argv[1]}")
PY
fi

echo "Environment OK."
echo "  backend:  $BACKEND_ENV (DATABASE_URL=$(redact_url "$DATABASE_URL_VALUE"))"
echo "  frontend: $FRONTEND_ENV (NEXT_PUBLIC_API_URL=$API_URL_VALUE, NEXT_PUBLIC_WS_URL=$WS_URL_VALUE)"
if [[ "$MODE" == "postgres-docker" ]]; then
  echo "  NOTE: run 'docker compose up -d' before starting the app. If POSTGRES_USER/PASSWORD/DB are overridden in the root .env or shell, update backend/.env to match."
fi
echo "Next: ./scripts/dev.sh"
