"""Poll MSSQL every 30 min; run route_sales_by_item_customer ETL when server is back."""
import os, sys, time, socket, subprocess
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

SERVER = os.environ['DB_SERVER']
INTERVAL = 30 * 60  # 30 minutes


def is_reachable():
    try:
        s = socket.create_connection((SERVER, 1433), timeout=10)
        s.close()
        return True
    except Exception:
        return False


def run_etl():
    print(f"[{time.strftime('%H:%M:%S')}] MSSQL is back! Running ETL for route_sales_by_item_customer ...", flush=True)
    result = subprocess.run(
        [sys.executable, 'etl/extract.py',
         '--table', 'route_sales_by_item_customer',
         '--from-date', '2026-02-01',
         '--to-date', '2026-02-28'],
        cwd=os.path.join(os.path.dirname(__file__), '..'),
    )
    if result.returncode == 0:
        print(f"[{time.strftime('%H:%M:%S')}] ETL completed successfully.", flush=True)
    else:
        print(f"[{time.strftime('%H:%M:%S')}] ETL failed with code {result.returncode}.", flush=True)
    return result.returncode == 0


attempt = 0
while True:
    attempt += 1
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    if is_reachable():
        print(f"[{ts}] Attempt {attempt}: MSSQL reachable.", flush=True)
        success = run_etl()
        if success:
            print("Done. Exiting.", flush=True)
            sys.exit(0)
        else:
            print(f"ETL failed — will retry in 30 min.", flush=True)
    else:
        print(f"[{ts}] Attempt {attempt}: MSSQL unreachable. Next check in 30 min.", flush=True)
    time.sleep(INTERVAL)
