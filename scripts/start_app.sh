#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
FRONTEND_DIR="$REPO_ROOT/frontend"
BACKEND_VENV_BIN="$BACKEND_DIR/.venv/bin"
DEFAULT_DATABASE_URL="postgresql+asyncpg://odte_user:odte_password@127.0.0.1:55432/odte_gex"

fail() {
  echo "Error: $*" >&2
  exit 1
}

require_file() {
  local path="$1"
  [[ -f "$path" ]] || fail "Required file not found: $path"
}

require_command() {
  local command_name="$1"
  command -v "$command_name" >/dev/null 2>&1 || fail "Required command not found: $command_name"
}

detect_terminal() {
  if command -v gnome-terminal >/dev/null 2>&1; then
    echo "gnome-terminal"
    return
  fi

  if command -v x-terminal-emulator >/dev/null 2>&1; then
    echo "x-terminal-emulator"
    return
  fi

  if command -v konsole >/dev/null 2>&1; then
    echo "konsole"
    return
  fi

  if command -v xfce4-terminal >/dev/null 2>&1; then
    echo "xfce4-terminal"
    return
  fi

  fail "No supported terminal launcher found."
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

wait_for_database() {
  local host="$1"
  local port="$2"

  python3 - "$host" "$port" <<'PY'
import socket
import sys
import time

host = sys.argv[1]
port = int(sys.argv[2])

deadline = time.time() + 60
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

launch_terminal() {
  local terminal_app="$1"
  local title="$2"
  local script_path="$3"
  local command_string

  command_string="$(printf '%q' "$script_path")"

  case "$terminal_app" in
    gnome-terminal)
      gnome-terminal --window --title="$title" --working-directory="$REPO_ROOT" -- bash -lc "$command_string"
      ;;
    x-terminal-emulator)
      x-terminal-emulator -T "$title" -e bash -lc "$command_string"
      ;;
    konsole)
      konsole --new-tab -p "tabtitle=$title" -e bash -lc "$command_string" &
      ;;
    xfce4-terminal)
      xfce4-terminal --title="$title" --working-directory="$REPO_ROOT" --command="bash -lc $command_string" &
      ;;
    *)
      fail "Unsupported terminal launcher: $terminal_app"
      ;;
  esac
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

require_file "$BACKEND_DIR/.env"
require_file "$BACKEND_DIR/.venv/bin/alembic"
require_file "$BACKEND_DIR/.venv/bin/uvicorn"
require_file "$REPO_ROOT/scripts/cleanup_runtime_state.sh"
require_command python3
require_command pnpm

"$REPO_ROOT/scripts/cleanup_runtime_state.sh"

TERMINAL_APP="$(detect_terminal)"
DATABASE_URL_VALUE="$(read_database_url)"
mapfile -t DB_ENDPOINT < <(parse_database_endpoint "$DATABASE_URL_VALUE")
DB_HOST="${DB_ENDPOINT[0]}"
DB_PORT="${DB_ENDPOINT[1]}"
DB_MODE="$(determine_db_mode "$DB_HOST" "$DB_PORT")"

case "$DB_MODE" in
  local)
    launch_terminal "$TERMINAL_APP" "ODTE DB" "$REPO_ROOT/scripts/run_local_db_terminal.sh"
    ;;
  external)
    echo "External database configured at $DB_HOST:$DB_PORT. No DB terminal launched."
    ;;
esac

echo "Waiting for database at $DB_HOST:$DB_PORT ..."
wait_for_database "$DB_HOST" "$DB_PORT" || fail "Database did not become reachable."

echo "Running backend migrations..."
(
  cd "$BACKEND_DIR"
  "$BACKEND_VENV_BIN/alembic" upgrade head
)

launch_terminal "$TERMINAL_APP" "ODTE Backend" "$REPO_ROOT/scripts/run_backend_dev.sh"
launch_terminal "$TERMINAL_APP" "ODTE Frontend" "$REPO_ROOT/scripts/run_frontend_dev.sh"

echo "All services launched."
echo "  Database: $DB_MODE ($DB_HOST:$DB_PORT)"
echo "  Backend: http://localhost:8000"
echo "  Frontend: http://localhost:3000"
