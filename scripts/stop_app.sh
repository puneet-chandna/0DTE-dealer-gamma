#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${ODTE_RUNTIME_DIR:-$REPO_ROOT/.local-run}"
FRONTEND_PID_FILE="$RUNTIME_DIR/frontend.pid"
BACKEND_PID_FILE="$RUNTIME_DIR/backend.pid"
DB_TERMINAL_PID_FILE="$RUNTIME_DIR/db_terminal.pid"

wait_for_exit() {
  local pid="$1"
  local attempts="${2:-20}"

  while (( attempts > 0 )); do
    if ! kill -0 "$pid" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
    attempts=$((attempts - 1))
  done

  return 1
}

stop_pid_file() {
  local label="$1"
  local pid_file="$2"
  local signal="${3:-INT}"

  if [[ ! -f "$pid_file" ]]; then
    echo "$label is not recorded as running."
    return 0
  fi

  local pid
  pid="$(<"$pid_file")"

  if [[ -z "$pid" ]] || ! [[ "$pid" =~ ^[0-9]+$ ]]; then
    echo "$label PID file is invalid. Cleaning it up."
    rm -f "$pid_file"
    return 0
  fi

  if ! kill -0 "$pid" >/dev/null 2>&1; then
    echo "$label is already stopped."
    rm -f "$pid_file"
    return 0
  fi

  echo "Stopping $label (PID $pid) ..."
  kill "-$signal" "$pid" >/dev/null 2>&1 || true

  if wait_for_exit "$pid"; then
    echo "$label stopped cleanly."
    rm -f "$pid_file"
    return 0
  fi

  echo "$label did not stop after SIG$signal, sending SIGTERM ..."
  kill -TERM "$pid" >/dev/null 2>&1 || true

  if wait_for_exit "$pid" 10; then
    echo "$label stopped after SIGTERM."
    rm -f "$pid_file"
    return 0
  fi

  echo "Warning: $label is still running. Please inspect it manually."
  return 1
}

mkdir -p "$RUNTIME_DIR"

stop_pid_file "frontend" "$FRONTEND_PID_FILE"
stop_pid_file "backend" "$BACKEND_PID_FILE"

if [[ -f "$DB_TERMINAL_PID_FILE" ]]; then
  stop_pid_file "database terminal" "$DB_TERMINAL_PID_FILE"
else
  echo "Database terminal PID not found. Attempting direct local Postgres shutdown ..."
  "$REPO_ROOT/scripts/stop_local_postgres.sh"
fi

echo "Stop sequence complete."
