#!/bin/zsh
# Export last 30 days of data from local PostgreSQL for Railway import.
# Usage: ./export_30days.sh
# Output: /tmp/nfpc_export/ (CSV files + schema SQL)

set -euo pipefail

PSQL="/opt/homebrew/Cellar/postgresql@17/17.9/bin/psql"
PG_DUMP="/opt/homebrew/Cellar/postgresql@17/17.9/bin/pg_dump"
DB="nfpc_reports"
EXPORT_DIR="/tmp/nfpc_export"
CUTOFF=$(date -v-30d +%Y-%m-%d)

echo "=== NFPC Export - Last 30 days (since $CUTOFF) ==="
rm -rf "$EXPORT_DIR"
mkdir -p "$EXPORT_DIR"

# 1. Export schema (no data)
echo "Exporting schema..."
$PG_DUMP -d "$DB" --schema-only --no-owner --no-privileges > "$EXPORT_DIR/schema.sql"

# 2. Fact tables - filtered by date column
export_filtered() {
    local tbl=$1 date_col=$2
    echo "Exporting $tbl (${date_col} >= $CUTOFF)..."
    $PSQL -d "$DB" -c "\\copy (SELECT * FROM $tbl WHERE $date_col >= '$CUTOFF') TO '$EXPORT_DIR/$tbl.csv' CSV HEADER"
    local rows=$(wc -l < "$EXPORT_DIR/$tbl.csv")
    echo "  -> $((rows - 1)) rows"
}

export_filtered rpt_sales_detail trx_date
export_filtered rpt_daily_sales_summary date
export_filtered rpt_collections receipt_date
export_filtered rpt_customer_visits date
export_filtered rpt_journeys date
export_filtered rpt_coverage_summary visit_date
export_filtered rpt_outstanding trx_date
export_filtered rpt_eot trip_date
export_filtered rpt_journey_plan date
export_filtered rpt_route_sales_collection date

# 3. Dimension / small tables - full export
for tbl in dim_channel dim_city dim_country dim_customer dim_item dim_region dim_route dim_sales_org dim_user rpt_targets rpt_holidays; do
    echo "Exporting $tbl (full)..."
    $PSQL -d "$DB" -c "\\copy $tbl TO '$EXPORT_DIR/$tbl.csv' CSV HEADER"
    rows=$(wc -l < "$EXPORT_DIR/$tbl.csv")
    echo "  -> $((rows - 1)) rows"
done

# 4. Summary
echo ""
echo "=== Export complete ==="
echo "Output directory: $EXPORT_DIR"
du -sh "$EXPORT_DIR"
echo ""
echo "Files:"
ls -lh "$EXPORT_DIR"/*.csv | awk '{print $5, $9}'
echo ""
echo "Next steps:"
echo "  1. Create Railway Postgres and get DATABASE_URL"
echo "  2. Load schema:  psql \$RAILWAY_URL < $EXPORT_DIR/schema.sql"
echo "  3. Load data:    ./import_railway.sh \$RAILWAY_URL"
