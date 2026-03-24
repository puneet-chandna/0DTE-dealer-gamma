#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PG_BIN_DIR="${PG_BIN_DIR:-/usr/lib/postgresql/17/bin}"
PGDATA_DIR="${PGDATA_DIR:-$REPO_ROOT/.local-postgres/data}"
PGSOCKET_DIR="${PGSOCKET_DIR:-$REPO_ROOT/.local-postgres/run}"
PGLOG_FILE="${PGLOG_FILE:-$REPO_ROOT/.local-postgres/postgres.log}"
PGPORT="${PGPORT:-55432}"

if [[ ! -x "$PG_BIN_DIR/pg_ctl" ]]; then
  echo "Missing required PostgreSQL control binary: $PG_BIN_DIR/pg_ctl" >&2
  exit 1
fi

if [[ ! -d "$PGDATA_DIR" || ! -f "$PGDATA_DIR/PG_VERSION" ]]; then
  echo "PostgreSQL data directory is not initialized: $PGDATA_DIR" >&2
  exit 1
fi

mkdir -p "$PGSOCKET_DIR"
mkdir -p "$(dirname "$PGLOG_FILE")"

if "$PG_BIN_DIR/pg_ctl" -D "$PGDATA_DIR" status >/dev/null 2>&1; then
  echo "Local PostgreSQL is already running for data directory: $PGDATA_DIR"
  exit 0
fi

"$PG_BIN_DIR/pg_ctl" \
  -D "$PGDATA_DIR" \
  -l "$PGLOG_FILE" \
  -o "-p $PGPORT -k $PGSOCKET_DIR -c listen_addresses=127.0.0.1" \
  start
