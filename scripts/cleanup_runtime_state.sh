#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${ODTE_RUNTIME_DIR:-$REPO_ROOT/.local-run}"
PID_FILES=("frontend.pid" "backend.pid" "db_terminal.pid")

mkdir -p "$RUNTIME_DIR"

for pid_filename in "${PID_FILES[@]}"; do
  pid_file="$RUNTIME_DIR/$pid_filename"

  if [[ ! -f "$pid_file" ]]; then
    continue
  fi

  pid_value="$(<"$pid_file")"

  if [[ -z "$pid_value" ]] || ! [[ "$pid_value" =~ ^[0-9]+$ ]]; then
    rm -f "$pid_file"
    continue
  fi

  if ! kill -0 "$pid_value" >/dev/null 2>&1; then
    rm -f "$pid_file"
  fi
done
