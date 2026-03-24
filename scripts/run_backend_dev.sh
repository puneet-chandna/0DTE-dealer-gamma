#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
VENV_BIN_DIR="$BACKEND_DIR/.venv/bin"
RUNTIME_DIR="${ODTE_RUNTIME_DIR:-$REPO_ROOT/.local-run}"
PID_FILE="$RUNTIME_DIR/backend.pid"
SERVICE_PID=""

cleanup_pid_file() {
  rm -f "$PID_FILE"
}

hold_terminal() {
  local exit_code="$1"
  cleanup_pid_file
  echo
  if [[ "$exit_code" -eq 0 ]]; then
    echo "Backend session stopped."
  else
    echo "Backend session exited with status $exit_code."
  fi
  printf "Press Enter to close this terminal..."
  read -r || true
}

trap 'hold_terminal "$?"' EXIT

if [[ ! -x "$VENV_BIN_DIR/alembic" || ! -x "$VENV_BIN_DIR/uvicorn" ]]; then
  echo "Backend virtual environment is missing required executables."
  echo "Expected: $VENV_BIN_DIR/alembic and $VENV_BIN_DIR/uvicorn"
  exit 1
fi

mkdir -p "$RUNTIME_DIR"

cd "$BACKEND_DIR"
echo "Applying backend migrations..."
"$VENV_BIN_DIR/alembic" upgrade head
echo "Starting backend on http://localhost:8000 ..."
"$VENV_BIN_DIR/uvicorn" app.main:app --reload &
SERVICE_PID="$!"
printf '%s\n' "$SERVICE_PID" > "$PID_FILE"
wait "$SERVICE_PID"
