"""
db.py — DashClip V4
PostgreSQL connection using DATABASE_URL env var.
Works with local PostgreSQL and Supabase PostgreSQL identically.
"""
import os
import psycopg2
import psycopg2.extras
from urllib.parse import urlparse

DATABASE_URL = os.getenv("DATABASE_URL", "")

def _build_conn_kwargs() -> dict:
    """Build psycopg2 connection kwargs from DATABASE_URL or individual vars."""
    if DATABASE_URL:
        # Parse the URL — handles both postgres:// and postgresql://
        url = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        parsed = urlparse(url)
        kwargs = {
            "host":     parsed.hostname,
            "port":     parsed.port or 5432,
            "dbname":   parsed.path.lstrip("/"),
            "user":     parsed.username,
            "password": parsed.password,
        }
        # Supabase requires SSL
        if parsed.hostname and "supabase" in parsed.hostname:
            kwargs["sslmode"] = "require"
        return kwargs
    else:
        # Fallback to individual env vars (local dev)
        return {
            "host":     os.getenv("DB_HOST", "localhost"),
            "port":     int(os.getenv("DB_PORT", "5432")),
            "dbname":   os.getenv("DB_NAME", "ai_script_video"),
            "user":     os.getenv("DB_USER", "postgres"),
            "password": os.getenv("DB_PASSWORD", ""),
        }

def get_db():
    """Get a new PostgreSQL connection. Caller must close it."""
    kwargs = _build_conn_kwargs()
    conn = psycopg2.connect(**kwargs)
    conn.autocommit = False
    return conn

def execute(conn, sql: str, params: tuple = ()):
    """Execute a SQL statement and return first row as dict or None."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(sql, params)
    try:
        row = cur.fetchone()
        return dict(row) if row else None
    except psycopg2.ProgrammingError:
        return None

def fetchone(conn, sql: str, params: tuple = ()):
    """Fetch a single row as dict."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(sql, params)
    row = cur.fetchone()
    return dict(row) if row else None

def fetchall(conn, sql: str, params: tuple = ()):
    """Fetch all rows as list of dicts."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]
