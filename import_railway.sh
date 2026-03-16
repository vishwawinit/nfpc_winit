#!/bin/bash
# Import exported CSV data into Railway PostgreSQL.
# Usage: ./import_railway.sh <DATABASE_URL>
# Run export_30days.sh first.

set -euo pipefail

if [ -z "${1:-}" ]; then
    echo "Usage: ./import_railway.sh <DATABASE_URL>"
    echo "Example: ./import_railway.sh postgresql://user:pass@host:port/dbname"
    exit 1
fi

DB_URL="$1"
EXPORT_DIR="/tmp/nfpc_export"

if [ ! -d "$EXPORT_DIR" ]; then
    echo "Error: $EXPORT_DIR not found. Run ./export_30days.sh first."
    exit 1
fi

echo "=== Loading schema ==="
psql "$DB_URL" < "$EXPORT_DIR/schema.sql"

echo ""
echo "=== Loading data ==="

for csv in "$EXPORT_DIR"/*.csv; do
    tbl=$(basename "$csv" .csv)
    echo "Loading $tbl..."
    psql "$DB_URL" -c "\\copy $tbl FROM '$csv' CSV HEADER"
    count=$(psql "$DB_URL" -t -c "SELECT COUNT(*) FROM $tbl;")
    echo "  -> $count rows"
done

echo ""
echo "=== Import complete ==="
psql "$DB_URL" -c "SELECT schemaname, tablename, n_live_tup FROM pg_stat_user_tables ORDER BY n_live_tup DESC;"
