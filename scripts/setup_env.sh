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
BACKEND_EXAMPLE="$REPO_ROOT/backend/.env.example"
BACKEND_ENV="$REPO_ROOT/backend/.env"
FRONTEND_EXAMPLE="$REPO_ROOT/frontend/.env.example"
FRONTEND_ENV="$REPO_ROOT/frontend/.env.local"
ROOT_ENV="$REPO_ROOT/.env"

SQLITE_URL="sqlite+aiosqlite:///./odte_gex.db"
POSTGRES_LOCAL_URL="postgresql+asyncpg://odte_user:odte_password@127.0.0.1:55432/odte_gex"
POSTGRES_DOCKER_URL="postgresql+asyncpg://odte_user:your_secure_password_here@localhost:5432/odte_gex"

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
  local file="$1"
  local name="$2"
  awk -F= -v key="$name" '$1 == key {sub(/^[^=]*=/, ""); print; exit}' "$file" 2>/dev/null || true
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
  local file="$1"
  local url="$2"
  local tmp_file="$file.tmp.$$"

  if grep -qE '^[[:space:]]*DATABASE_URL=' "$file"; then
    sed -E "s#^[[:space:]]*DATABASE_URL=.*#DATABASE_URL=${url}#" "$file" > "$tmp_file"
  else
    cp "$file" "$tmp_file"
    printf 'DATABASE_URL=%s\n' "$url" >> "$tmp_file"
  fi
  mv "$tmp_file" "$file"
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

ensure_from_example "$BACKEND_EXAMPLE" "$BACKEND_ENV" "backend env"
ensure_from_example "$FRONTEND_EXAMPLE" "$FRONTEND_ENV" "frontend env"

if [[ "$MODE_EXPLICIT" -eq 1 ]]; then
  set_database_url "$BACKEND_ENV" "$WANT_URL"
  echo "Set DATABASE_URL for mode '$MODE' in $BACKEND_ENV"
fi

# --- validation (fail fast with a clear message) ---
DATABASE_URL_VALUE="$(read_var "$BACKEND_ENV" "DATABASE_URL")"
[[ -n "$DATABASE_URL_VALUE" ]] || fail "DATABASE_URL is missing or empty in $BACKEND_ENV. Set it to '$SQLITE_URL' for the zero-setup SQLite default."
if ! [[ "$DATABASE_URL_VALUE" == sqlite* || "$DATABASE_URL_VALUE" == postgresql* || "$DATABASE_URL_VALUE" == postgres:* ]]; then
  fail "DATABASE_URL in $BACKEND_ENV has an unsupported scheme: '$(redact_url "$DATABASE_URL_VALUE")'. Use a 'sqlite:' URL or a 'postgresql:' URL."
fi

API_URL_VALUE="$(read_var "$FRONTEND_ENV" "NEXT_PUBLIC_API_URL")"
[[ -n "$API_URL_VALUE" ]] || fail "NEXT_PUBLIC_API_URL is missing or empty in $FRONTEND_ENV. Expected e.g. 'http://localhost:8000'."

WS_URL_VALUE="$(read_var "$FRONTEND_ENV" "NEXT_PUBLIC_WS_URL")"
[[ -n "$WS_URL_VALUE" ]] || fail "NEXT_PUBLIC_WS_URL is missing or empty in $FRONTEND_ENV. Expected e.g. 'ws://localhost:8000/ws'."

# --- stale provider key cleanup (root .env only, never touch app env files) ---
if [[ -f "$ROOT_ENV" ]] && grep -q 'POLYGON_API_KEY' "$ROOT_ENV"; then
  sed -i '/POLYGON_API_KEY/d' "$ROOT_ENV"
  echo "Removed stale POLYGON_API_KEY from $ROOT_ENV"
fi

echo "Environment OK (mode: $MODE)."
echo "  backend:  $BACKEND_ENV (DATABASE_URL=$(redact_url "$DATABASE_URL_VALUE"))"
echo "  frontend: $FRONTEND_ENV (NEXT_PUBLIC_API_URL=$API_URL_VALUE, NEXT_PUBLIC_WS_URL=$WS_URL_VALUE)"
if [[ "$MODE" == "postgres-docker" ]]; then
  echo "  NOTE: update the placeholder password in DATABASE_URL and run 'docker compose up -d' before starting the app."
fi
echo "Next: ./scripts/dev.sh"
