#!/usr/bin/env python3
"""
Execute SP_tblTrxHeader_ReportCountryView with correct parameters for March 2026.
Parameters:
  @CountryId    = '' (all countries, empty = no filter per SP logic)
  @SearchString = WHERE clause fragment injected into dynamic SQL
  @UserCode     = 'admin'
"""

import pymssql

DB_CONFIG = {
    "server": "20.203.45.86",
    "user": "nfpc",
    "password": "nfpc@!23",
    "database": "NFPCsfaV3_070326",
    "timeout": 60,
    "login_timeout": 15,
}

OUTPUT_FILE = "/Users/mac/Downloads/nfpc-reports-main/etl/logs/sp_market_sales.txt"


def print_result_sets(cursor, label=""):
    result_num = 1
    while True:
        try:
            cols = [desc[0] for desc in cursor.description] if cursor.description else []
            if not cols:
                if not cursor.nextset():
                    break
                continue

            rows = cursor.fetchall()
            print(f"\n  --- Result Set #{result_num} {label} — {len(rows)} rows, {len(cols)} cols ---")
            print(f"  Columns: {cols}")

            col_widths = [max(len(str(c)), 10) for c in cols]
            for r in rows[:5]:
                for j, val in enumerate(r):
                    col_widths[j] = max(col_widths[j], len(str(val)[:60]))

            header_line = " | ".join(str(c).ljust(col_widths[i]) for i, c in enumerate(cols))
            print("  " + header_line)
            print("  " + "-" * len(header_line))
            for row in rows[:5]:
                print("  " + " | ".join(str(v)[:60].ljust(col_widths[i]) for i, v in enumerate(row)))
            if len(rows) > 5:
                print(f"  ... ({len(rows) - 5} more rows)")

            result_num += 1
            if not cursor.nextset():
                break
        except StopIteration:
            break
        except Exception as e:
            print(f"  [nextset error]: {e}")
            break


conn = pymssql.connect(**DB_CONFIG)
print("Connected.\n")

attempts = [
    # All countries, March 2026 date filter, admin user
    {
        "label": "All countries, March 2026, admin",
        "country_id": "",
        "search": "T.TrxDate >= '2026-03-01' AND T.TrxDate < '2026-04-01'",
        "user": "admin",
    },
    # All countries, no date filter (all data), admin
    {
        "label": "All countries, no date filter, admin",
        "country_id": "",
        "search": "1=1",
        "user": "admin",
    },
    # Specific countries UAE(42) and OMAN(51), March 2026
    {
        "label": "UAE+OMAN (42,51), March 2026, admin",
        "country_id": "42,51",
        "search": "T.TrxDate >= '2026-03-01' AND T.TrxDate < '2026-04-01'",
        "user": "admin",
    },
    # UAE+OMAN, no date filter
    {
        "label": "UAE+OMAN (42,51), no date filter, admin",
        "country_id": "42,51",
        "search": "1=1",
        "user": "admin",
    },
]

success = False
for a in attempts:
    sql = "EXEC SP_tblTrxHeader_ReportCountryView %s, %s, %s"
    display = f"EXEC SP_tblTrxHeader_ReportCountryView '{a['country_id']}', '{a['search']}', '{a['user']}'"
    print(f"\nAttempt: {a['label']}")
    print(f"SQL    : {display}")
    cursor = conn.cursor()
    try:
        cursor.execute(sql, (a["country_id"], a["search"], a["user"]))
        print_result_sets(cursor, f"[{a['label']}]")
        success = True
        # Write to output file (append)
        with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
            f.write("\n" + "=" * 100 + "\n")
            f.write(f"  SP_tblTrxHeader_ReportCountryView — EXECUTION RESULTS\n")
            f.write("=" * 100 + "\n")
            f.write(f"  Attempt  : {a['label']}\n")
            f.write(f"  SQL      : {display}\n")
            f.write(f"  CountryId: {a['country_id']}\n")
            f.write(f"  Search   : {a['search']}\n")
            f.write(f"  UserCode : {a['user']}\n\n")
        print("\n  [Results appended to sp_market_sales.txt]")
        break
    except Exception as e:
        print(f"  [FAILED]: {e}")

if not success:
    print("\n[WARNING] All execution attempts for SP_tblTrxHeader_ReportCountryView failed.")

conn.close()
print("\nDone.")
