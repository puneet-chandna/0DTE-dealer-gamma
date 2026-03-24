#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PG_BIN_DIR="${PG_BIN_DIR:-/usr/lib/postgresql/17/bin}"
PGDATA_DIR="${PGDATA_DIR:-$REPO_ROOT/.local-postgres/data}"

if [[ ! -d "$PGDATA_DIR" ]]; then
  echo "Local Postgres data directory not found. Nothing to stop."
  exit 0
fi

if ! "$PG_BIN_DIR/pg_ctl" -D "$PGDATA_DIR" status >/dev/null 2>&1; then
  echo "Local Postgres is already stopped."
  exit 0
fi

"$PG_BIN_DIR/pg_ctl" -D "$PGDATA_DIR" stop -m smart
