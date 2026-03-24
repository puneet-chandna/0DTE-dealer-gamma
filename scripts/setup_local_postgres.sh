#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PG_BIN_DIR="${PG_BIN_DIR:-/usr/lib/postgresql/17/bin}"
PGDATA_DIR="${PGDATA_DIR:-$REPO_ROOT/.local-postgres/data}"
PGSOCKET_DIR="${PGSOCKET_DIR:-$REPO_ROOT/.local-postgres/run}"
PGLOG_FILE="${PGLOG_FILE:-$REPO_ROOT/.local-postgres/postgres.log}"
PGPORT="${PGPORT:-55432}"
PGUSER_NAME="${PGUSER_NAME:-odte_user}"
PGPASSWORD_VALUE="${PGPASSWORD_VALUE:-odte_password}"
PGDATABASE_NAME="${PGDATABASE_NAME:-odte_gex}"

require_bin() {
  local bin_name="$1"
  if [[ ! -x "$PG_BIN_DIR/$bin_name" ]]; then
    echo "Missing required binary: $PG_BIN_DIR/$bin_name" >&2
    exit 1
  fi
}

sql_escape_literal() {
  local value="$1"
  printf "%s" "${value//\'/\'\'}"
}

wait_for_ready() {
  local attempt
  for attempt in $(seq 1 20); do
    if "$PG_BIN_DIR/pg_isready" -h 127.0.0.1 -p "$PGPORT" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done

  echo "Local Postgres did not become ready on port $PGPORT" >&2
  exit 1
}

require_bin initdb
require_bin pg_ctl
require_bin psql
require_bin createdb
require_bin pg_isready

mkdir -p "$(dirname "$PGDATA_DIR")" "$PGSOCKET_DIR"

if [[ ! -f "$PGDATA_DIR/PG_VERSION" ]]; then
  mkdir -p "$PGDATA_DIR"
  "$PG_BIN_DIR/initdb" \
    -D "$PGDATA_DIR" \
    -U "$PGUSER_NAME" \
    --auth-local=trust \
    --auth-host=scram-sha-256 >/dev/null
fi

if ! "$PG_BIN_DIR/pg_ctl" -D "$PGDATA_DIR" status >/dev/null 2>&1; then
  "$PG_BIN_DIR/pg_ctl" \
    -D "$PGDATA_DIR" \
    -l "$PGLOG_FILE" \
    -o "-p $PGPORT -k $PGSOCKET_DIR -c listen_addresses=127.0.0.1" \
    start >/dev/null
fi

wait_for_ready

escaped_password="$(sql_escape_literal "$PGPASSWORD_VALUE")"

"$PG_BIN_DIR/psql" \
  -h "$PGSOCKET_DIR" \
  -p "$PGPORT" \
  -U "$PGUSER_NAME" \
  -d postgres \
  -v ON_ERROR_STOP=1 \
  -c "ALTER ROLE \"$PGUSER_NAME\" WITH PASSWORD '$escaped_password';" >/dev/null

db_exists="$("$PG_BIN_DIR/psql" \
  -h "$PGSOCKET_DIR" \
  -p "$PGPORT" \
  -U "$PGUSER_NAME" \
  -d postgres \
  -tAc "SELECT 1 FROM pg_database WHERE datname = '$(sql_escape_literal "$PGDATABASE_NAME")';")"

if [[ "$db_exists" != "1" ]]; then
  "$PG_BIN_DIR/createdb" \
    -h "$PGSOCKET_DIR" \
    -p "$PGPORT" \
    -U "$PGUSER_NAME" \
    "$PGDATABASE_NAME"
fi

echo "Local Postgres is ready."
echo "  Data dir: $PGDATA_DIR"
echo "  Socket dir: $PGSOCKET_DIR"
echo "  Port: $PGPORT"
echo "  Database: $PGDATABASE_NAME"
echo "  User: $PGUSER_NAME"
