#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$REPO_ROOT/frontend"
RUNTIME_DIR="${ODTE_RUNTIME_DIR:-$REPO_ROOT/.local-run}"
PID_FILE="$RUNTIME_DIR/frontend.pid"
SERVICE_PID=""

cleanup_pid_file() {
  rm -f "$PID_FILE"
}

hold_terminal() {
  local exit_code="$1"
  cleanup_pid_file
  echo
  if [[ "$exit_code" -eq 0 ]]; then
    echo "Frontend session stopped."
  else
    echo "Frontend session exited with status $exit_code."
  fi
  printf "Press Enter to close this terminal..."
  read -r || true
}

trap 'hold_terminal "$?"' EXIT

if ! command -v pnpm >/dev/null 2>&1; then
  echo "pnpm is not installed or not on PATH."
  exit 1
fi

mkdir -p "$RUNTIME_DIR"

cd "$FRONTEND_DIR"
echo "Starting frontend on http://localhost:3000 ..."
pnpm dev &
SERVICE_PID="$!"
printf '%s\n' "$SERVICE_PID" > "$PID_FILE"
wait "$SERVICE_PID"
