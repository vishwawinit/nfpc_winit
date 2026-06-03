#!/usr/bin/env python3
"""
Sync tblUser, tblUserDetails, tblUserRole from MSSQL -> Railway PostgreSQL.

Phase 1: Print MSSQL column definitions for all three tables.
Phase 2: Create matching tables in PostgreSQL (DROP + CREATE each run).
Phase 3: Bulk-copy all rows from MSSQL to PostgreSQL.

Run manually:  python etl/etl/sync_user_tables.py
READ-ONLY on MSSQL -- no writes to source DB.
"""

import sys
import pymssql
import psycopg2
from psycopg2.extras import execute_values

# ── MSSQL connection (READ-ONLY source) ──────────────────────────────────────
MSSQL_CFG = dict(
    server   = 'winitdb01.NFPC.NET',
    port     = 1433,
    user     = 'nfpcsfa',
    password = '123456_NfpcNfpc',
    database = 'NFPCsfaV3',
    timeout  = 30,
)

# ── Railway PostgreSQL (write target) ────────────────────────────────────────
PG_CFG = dict(
    host     = 'switchback.proxy.rlwy.net',
    port     = 31910,
    dbname   = 'railway',
    user     = 'postgres',
    password = 'glzENZuNPmfnAEYrprneXIfVczZAfExC',
)

# Tables to sync: (MSSQL source name, PostgreSQL target name)
TABLES = [
    ('tblUserRole',    'tbl_user_role'),
    ('tblUser',        'tbl_user'),
    ('tblUserDetails', 'tbl_user_details'),
]


# ── MSSQL -> PostgreSQL type mapping ─────────────────────────────────────────
def mssql_to_pg_type(mssql_type, max_length, precision, scale):
    t = (mssql_type or '').lower().strip()

    if t in ('nvarchar', 'varchar', 'nchar', 'char', 'sysname'):
        # CHARACTER_MAXIMUM_LENGTH is already in characters for all string types
        if max_length is None or max_length == -1:
            return 'TEXT'
        if max_length <= 0:
            return 'TEXT'
        return 'VARCHAR({})'.format(max_length)

    if t in ('int', 'integer'):
        return 'INTEGER'
    if t == 'bigint':
        return 'BIGINT'
    if t in ('smallint', 'tinyint'):
        return 'SMALLINT'
    if t == 'bit':
        return 'BOOLEAN'

    if t in ('decimal', 'numeric'):
        p = precision if precision and precision > 0 else 18
        s = scale if scale is not None and scale >= 0 else 4
        return 'NUMERIC({},{})'.format(p, s)

    if t == 'money':
        return 'NUMERIC(19,4)'
    if t == 'smallmoney':
        return 'NUMERIC(10,4)'
    if t in ('float', 'real'):
        return 'DOUBLE PRECISION'

    if t in ('datetime', 'datetime2', 'smalldatetime'):
        return 'TIMESTAMP'
    if t == 'date':
        return 'DATE'
    if t == 'time':
        return 'TIME'

    if t == 'uniqueidentifier':
        return 'TEXT'   # store as text to avoid UUID format issues
    if t in ('text', 'ntext'):
        return 'TEXT'
    if t in ('image', 'varbinary', 'binary'):
        return 'BYTEA'
    if t == 'xml':
        return 'TEXT'
    if t == 'sql_variant':
        return 'TEXT'

    # Unknown type — fallback to TEXT so sync never crashes
    return 'TEXT'


def coerce_value(val, pg_type):
    """Convert MSSQL Python value to something psycopg2 accepts."""
    if val is None:
        return None
    pt = pg_type.lower()
    if 'boolean' in pt:
        # pymssql returns BIT as int 0/1
        return bool(val)
    if 'bytea' in pt:
        return psycopg2.Binary(val)
    # Everything else (str, int, float, datetime, Decimal) psycopg2 handles natively
    return val


# ── Phase 1: Inspect MSSQL columns ──────────────────────────────────────────
def get_mssql_columns(ms_conn, table_name):
    cursor = ms_conn.cursor(as_dict=True)
    cursor.execute(
        """
        SELECT
            COLUMN_NAME,
            DATA_TYPE,
            CHARACTER_MAXIMUM_LENGTH,
            NUMERIC_PRECISION,
            NUMERIC_SCALE,
            IS_NULLABLE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = %s
        ORDER BY ORDINAL_POSITION
        """,
        (table_name,)
    )
    rows = cursor.fetchall()
    cursor.close()
    return rows


def print_columns(table_name, cols):
    print("\n" + "=" * 62)
    print("  MSSQL table: {}  ({} columns)".format(table_name, len(cols)))
    print("=" * 62)
    print("  {:<35} {:<22} {}".format("Column", "MSSQL Type", "Nullable"))
    print("  {:<35} {:<22} {}".format("-" * 35, "-" * 22, "-" * 8))
    for c in cols:
        length    = c['CHARACTER_MAXIMUM_LENGTH']
        prec      = c['NUMERIC_PRECISION']
        scale     = c['NUMERIC_SCALE']
        type_str  = c['DATA_TYPE']
        if length is not None:
            type_str += '(MAX)' if length == -1 else '({})'.format(length)
        elif prec is not None:
            type_str += '({},{})'.format(prec, scale if scale is not None else 0)
        print("  {:<35} {:<22} {}".format(
            c['COLUMN_NAME'], type_str, c['IS_NULLABLE']
        ))


# ── Phase 2: Create PostgreSQL tables ────────────────────────────────────────
def build_create_sql(pg_table, cols):
    col_defs = []
    for c in cols:
        col_name = '"{}"'.format(c['COLUMN_NAME'].lower())
        pg_type  = mssql_to_pg_type(
            c['DATA_TYPE'],
            c['CHARACTER_MAXIMUM_LENGTH'],
            c['NUMERIC_PRECISION'],
            c['NUMERIC_SCALE'],
        )
        nullable = '' if c['IS_NULLABLE'] == 'YES' else ' NOT NULL'
        col_defs.append('    {} {}{}'.format(col_name, pg_type, nullable))
    return 'CREATE TABLE {} (\n{}\n);'.format(pg_table, ',\n'.join(col_defs))


def create_pg_table(pg_conn, pg_table, create_sql):
    with pg_conn.cursor() as cur:
        cur.execute('DROP TABLE IF EXISTS {} CASCADE'.format(pg_table))
        cur.execute(create_sql)
    pg_conn.commit()
    print("  [PG] Created: {}".format(pg_table))


# ── Phase 3: Sync data ───────────────────────────────────────────────────────
def sync_table(ms_conn, pg_conn, ms_table, pg_table, cols):
    col_names_ms = [c['COLUMN_NAME'] for c in cols]
    col_names_pg = ['"{}"'.format(c.lower()) for c in col_names_ms]
    pg_types = [
        mssql_to_pg_type(
            c['DATA_TYPE'],
            c['CHARACTER_MAXIMUM_LENGTH'],
            c['NUMERIC_PRECISION'],
            c['NUMERIC_SCALE'],
        )
        for c in cols
    ]

    # Read all rows from MSSQL
    ms_cur = ms_conn.cursor(as_dict=True)
    ms_cur.execute('SELECT * FROM [{}]'.format(ms_table))
    rows = ms_cur.fetchall()
    ms_cur.close()

    if not rows:
        print("  [MSSQL] {}: 0 rows -- nothing to sync".format(ms_table))
        return

    # Coerce each value to the matching PostgreSQL type
    data = []
    for row in rows:
        data.append(tuple(
            coerce_value(row[col], pg_types[i])
            for i, col in enumerate(col_names_ms)
        ))

    # Bulk insert into PostgreSQL
    insert_sql = 'INSERT INTO {} ({}) VALUES %s'.format(
        pg_table, ', '.join(col_names_pg)
    )
    with pg_conn.cursor() as cur:
        execute_values(cur, insert_sql, data, page_size=500)
    pg_conn.commit()

    print("  [SYNC] {} -> {}: {} rows".format(ms_table, pg_table, len(data)))


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    print("\n" + "=" * 62)
    print("  NFPC User Tables Sync: MSSQL -> Railway PostgreSQL")
    print("=" * 62)

    # Connect MSSQL
    import socket
    host = MSSQL_CFG['server']
    print("\n[CONNECT] MSSQL: {}:{} / {} ...".format(
        host, MSSQL_CFG.get('port', 1433), MSSQL_CFG['database']
    ))
    try:
        ip = socket.gethostbyname(host)
        print("  Resolved {} -> {}".format(host, ip))
    except socket.gaierror as e:
        print("  DNS FAILED: cannot resolve '{}' -- {}".format(host, e))
        print("  Try updating MSSQL_CFG['server'] to the actual IP address.")
        sys.exit(1)
    try:
        ms_conn = pymssql.connect(**MSSQL_CFG)
        print("  OK")
    except Exception as e:
        print("  FAILED: {}".format(e))
        sys.exit(1)

    # Connect PostgreSQL
    print("[CONNECT] PostgreSQL: {}:{} / {} ...".format(
        PG_CFG['host'], PG_CFG['port'], PG_CFG['dbname']
    ))
    try:
        pg_conn = psycopg2.connect(**PG_CFG)
        pg_conn.autocommit = False
        print("  OK")
    except Exception as e:
        print("  FAILED: {}".format(e))
        ms_conn.close()
        sys.exit(1)

    # ── Phase 1: column inspection ───────────────────────────────────────────
    print("\n[PHASE 1] Reading MSSQL column definitions ...")
    table_cols = {}
    for ms_table, _ in TABLES:
        cols = get_mssql_columns(ms_conn, ms_table)
        if not cols:
            print("  WARNING: no columns found for '{}' "
                  "-- wrong table name or no permission".format(ms_table))
        else:
            table_cols[ms_table] = cols
            print_columns(ms_table, cols)

    if not table_cols:
        print("\nNo tables found. Exiting.")
        ms_conn.close()
        pg_conn.close()
        sys.exit(1)

    # ── Phase 2: create PostgreSQL tables ────────────────────────────────────
    print("\n\n[PHASE 2] Creating PostgreSQL tables ...")
    for ms_table, pg_table in TABLES:
        cols = table_cols.get(ms_table)
        if not cols:
            print("  Skipping {} (no column info)".format(pg_table))
            continue
        create_sql = build_create_sql(pg_table, cols)
        print("\n  DDL -> {}:\n{}".format(pg_table, create_sql))
        try:
            create_pg_table(pg_conn, pg_table, create_sql)
        except Exception as e:
            print("  ERROR creating {}: {}".format(pg_table, e))
            pg_conn.rollback()
            ms_conn.close()
            pg_conn.close()
            sys.exit(1)

    # ── Phase 3: sync data ───────────────────────────────────────────────────
    print("\n[PHASE 3] Syncing data ...")
    for ms_table, pg_table in TABLES:
        cols = table_cols.get(ms_table)
        if not cols:
            print("  Skipping {} (no column info)".format(ms_table))
            continue
        try:
            sync_table(ms_conn, pg_conn, ms_table, pg_table, cols)
        except Exception as e:
            print("  ERROR syncing {}: {}".format(ms_table, e))
            pg_conn.rollback()

    ms_conn.close()
    pg_conn.close()
    print("\nDone.\n")


if __name__ == '__main__':
    main()
