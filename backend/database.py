import sqlite3
from contextlib import contextmanager
from contextvars import ContextVar

from backend.config import DB_PATH, PLATFORM_DB_PATH

# Which company database the current request works against (set by the auth middleware).
# Defaults to the legacy single-company database so CLI scripts keep working.
current_db_path: ContextVar[str | None] = ContextVar("current_db_path", default=None)


def _open(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def connect(path: str | None = None) -> sqlite3.Connection:
    return _open(path or current_db_path.get() or DB_PATH)


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row else None


def rows_to_list(cursor: sqlite3.Cursor) -> list[dict]:
    return [dict(r) for r in cursor.fetchall()]


@contextmanager
def _transaction(conn: sqlite3.Connection):
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def get_db(path: str | None = None):
    """Connection to the current company's database."""
    with _transaction(connect(path)) as conn:
        yield conn


@contextmanager
def platform_db():
    """Connection to the platform database (companies, subscriptions, users, sessions)."""
    with _transaction(_open(PLATFORM_DB_PATH)) as conn:
        yield conn


def fetch_one(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> dict | None:
    return row_to_dict(conn.execute(sql, params).fetchone())


def fetch_all(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    return rows_to_list(conn.execute(sql, params))


def execute(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> sqlite3.Cursor:
    return conn.execute(sql, params)
