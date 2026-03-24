#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_FILE="${PGLOG_FILE:-$REPO_ROOT/.local-postgres/postgres.log}"
RUNTIME_DIR="${ODTE_RUNTIME_DIR:-$REPO_ROOT/.local-run}"
PID_FILE="$RUNTIME_DIR/db_terminal.pid"
TAIL_PID=""

cleanup_tail() {
  if [[ -n "$TAIL_PID" ]]; then
    kill "$TAIL_PID" >/dev/null 2>&1 || true
  fi
}

cleanup_state() {
  cleanup_tail
  rm -f "$PID_FILE"
}

stop_database() {
  echo
  echo "Stopping local Postgres..."
  cleanup_state
  "$REPO_ROOT/scripts/stop_local_postgres.sh" >/dev/null 2>&1 || true
  exit 0
}

trap cleanup_state EXIT
trap stop_database INT TERM HUP

mkdir -p "$RUNTIME_DIR"
printf '%s\n' "$$" > "$PID_FILE"

"$REPO_ROOT/scripts/setup_local_postgres.sh"

mkdir -p "$(dirname "$LOG_FILE")"
touch "$LOG_FILE"

echo "Streaming local Postgres logs."
echo "Press Ctrl+C in this terminal to stop the local database."

tail -n 40 -F "$LOG_FILE" &
TAIL_PID="$!"
wait "$TAIL_PID"
