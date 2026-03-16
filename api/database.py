"""Database connection pool for PostgreSQL with in-memory query caching."""
import os
import hashlib
import time
import json
from contextlib import contextmanager
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

_pool = None

# ---------- Simple TTL cache ----------
_cache = {}
CACHE_TTL = 300  # 5 minutes


def _cache_key(sql, params):
    """Create a hashable cache key from SQL + params."""
    raw = sql + json.dumps(params, default=str, sort_keys=True) if params else sql
    return hashlib.md5(raw.encode()).hexdigest()


def cache_clear():
    """Clear the entire query cache."""
    _cache.clear()


def _cache_get(key):
    entry = _cache.get(key)
    if entry is None:
        return None
    if time.time() - entry['ts'] > CACHE_TTL:
        del _cache[key]
        return None
    return entry['data']


def _cache_set(key, data):
    # Evict old entries if cache grows too large (> 500 entries)
    if len(_cache) > 500:
        now = time.time()
        expired = [k for k, v in _cache.items() if now - v['ts'] > CACHE_TTL]
        for k in expired:
            del _cache[k]
        # If still too large, drop oldest half
        if len(_cache) > 500:
            sorted_keys = sorted(_cache, key=lambda k: _cache[k]['ts'])
            for k in sorted_keys[:len(sorted_keys) // 2]:
                del _cache[k]
    _cache[key] = {'data': data, 'ts': time.time()}


# ---------- Connection pool ----------

def get_pool():
    global _pool
    if _pool is None:
        database_url = os.environ.get('DATABASE_URL')
        if database_url:
            _pool = ThreadedConnectionPool(minconn=2, maxconn=10, dsn=database_url)
        else:
            _pool = ThreadedConnectionPool(
                minconn=2,
                maxconn=10,
                host=os.environ.get('PG_HOST', 'localhost'),
                port=os.environ.get('PG_PORT', '5432'),
                dbname=os.environ['PG_DATABASE'],
                user=os.environ.get('PG_USER', 'fci'),
                password=os.environ.get('PG_PASSWORD', ''),
            )
    return _pool

@contextmanager
def get_db():
    pool = get_pool()
    conn = pool.getconn()
    try:
        yield conn
    finally:
        pool.putconn(conn)

def query(sql, params=None):
    """Execute a query and return list of dicts. Results are cached for 5 min."""
    key = _cache_key(sql, params)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
            result = [dict(zip(cols, row)) for row in rows]

    _cache_set(key, result)
    return result

def query_one(sql, params=None):
    """Execute a query and return a single dict. Results are cached for 5 min."""
    results = query(sql, params)
    return results[0] if results else None
