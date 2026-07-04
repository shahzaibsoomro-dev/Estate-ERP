import json
from backend.config import DEFAULT_SETTINGS
from backend.database import fetch_all, fetch_one


def get_all(conn) -> dict:
    rows = fetch_all(conn, "SELECT key, value FROM company_settings")
    settings = dict(DEFAULT_SETTINGS)
    settings.update({r["key"]: r["value"] for r in rows})
    return settings


def get(conn, key: str, default: str | None = None) -> str:
    row = fetch_one(conn, "SELECT value FROM company_settings WHERE key=?", (key,))
    if row:
        return row["value"]
    return default if default is not None else DEFAULT_SETTINGS.get(key, "")


def get_float(conn, key: str, default: float = 0.0) -> float:
    try:
        return float(get(conn, key, str(default)))
    except ValueError:
        return default


def get_bool(conn, key: str, default: bool = False) -> bool:
    return get(conn, key, str(default).lower()).lower() in ("true", "1", "yes")


def set_value(conn, key: str, value: str) -> dict:
    conn.execute(
        "INSERT OR REPLACE INTO company_settings(key, value) VALUES(?, ?)",
        (key, value),
    )
    return {"key": key, "value": value}
