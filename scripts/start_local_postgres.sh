#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PG_BIN_DIR="${PG_BIN_DIR:-/usr/lib/postgresql/17/bin}"
PGDATA_DIR="${PGDATA_DIR:-$REPO_ROOT/.local-postgres/data}"
PGSOCKET_DIR="${PGSOCKET_DIR:-$REPO_ROOT/.local-postgres/run}"
PGLOG_FILE="${PGLOG_FILE:-$REPO_ROOT/.local-postgres/postgres.log}"
PGPORT="${PGPORT:-55432}"

mkdir -p "$PGSOCKET_DIR"

"$PG_BIN_DIR/pg_ctl" \
  -D "$PGDATA_DIR" \
  -l "$PGLOG_FILE" \
  -o "-p $PGPORT -k $PGSOCKET_DIR -c listen_addresses=127.0.0.1" \
  start
