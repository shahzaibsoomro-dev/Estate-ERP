"""Browser first-run setup (runs against a fresh platform database)."""
import shutil
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
GOOD = "Quartz-Lamp-7713"


@pytest.fixture
def fresh(tmp_path, monkeypatch):
    import backend.auth.schema  # noqa: F401
    import backend.config as config
    import backend.database as database
    import backend.db.seed as seed
    import backend.saas.schema as schema
    import backend.saas.service as saas
    legacy = tmp_path / "haven.db"
    shutil.copy(ROOT / "db" / "haven.pre-sim.db", legacy)
    platform = tmp_path / "platform.db"
    for mod in (config, database, saas, seed):
        monkeypatch.setattr(mod, "DB_PATH", str(legacy), raising=False)
    monkeypatch.setattr(database, "PLATFORM_DB_PATH", str(platform))
    monkeypatch.setattr(schema, "PLATFORM_DB_PATH", str(platform))
    from backend.main import app
    with TestClient(app) as c:
        yield c, platform, legacy


def body(**over):
    b = {"superadmin": {"name": "Dev", "email": "dev@setup.test", "password": GOOD},
         "admin": {"name": "Owner", "email": "owner@setup.test", "password": GOOD + "x"},
         "company_name": "Haven Builders Pvt"}
    b.update(over)
    return b


def test_setup_blocked_for_remote_clients(fresh, monkeypatch):
    c, platform, _ = fresh
    monkeypatch.delenv("ERP_ALLOW_REMOTE_SETUP", raising=False)
    st = c.get("/api/setup/status").json()
    assert st["needed"] and st["allowed_here"] is False  # TestClient is not a loopback address
    assert c.post("/api/setup", json=body()).status_code == 403
    assert sqlite3.connect(platform).execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0


def test_setup_proxy_headers_are_not_trusted(fresh, monkeypatch):
    c, _, _ = fresh
    from backend.routers import setup as setup_router
    monkeypatch.setattr(setup_router, "LOOPBACK", {"testclient"})
    r = c.post("/api/setup", json=body(), headers={"X-Forwarded-For": "203.0.113.9"})
    assert r.status_code == 403


def test_setup_creates_both_accounts_once(fresh, monkeypatch):
    c, platform, legacy = fresh
    from backend.routers import setup as setup_router
    monkeypatch.setattr(setup_router, "LOOPBACK", {"testclient"})
    st = c.get("/api/setup/status").json()
    assert st["needed"] and st["allowed_here"] and st["company"]["projects"] > 0
    # validation happens before anything is stored
    bad = body(admin={"name": "Owner", "email": "dev@setup.test", "password": GOOD})
    assert c.post("/api/setup", json=bad).status_code == 400
    weak = body(superadmin={"name": "Dev", "email": "dev@setup.test", "password": "short"})
    assert c.post("/api/setup", json=weak).status_code == 400
    r = c.post("/api/setup", json=body())
    assert r.status_code == 200, r.text
    rows = sqlite3.connect(platform).execute("SELECT email, role, company_id, must_change_password FROM users ORDER BY id").fetchall()
    assert rows == [("dev@setup.test", "superadmin", None, 0), ("owner@setup.test", "admin", 1, 0)]
    assert sqlite3.connect(legacy).execute("SELECT value FROM company_settings WHERE key='company_name'").fetchone()[0] == "Haven Builders Pvt"
    # one-time only
    assert c.get("/api/setup/status").json() == {"needed": False}
    assert c.post("/api/setup", json=body(superadmin={"name": "X", "email": "x@setup.test", "password": GOOD})).status_code == 409
    # both can sign in and land in the right place
    me = c.post("/api/auth/login", json={"identifier": "owner@setup.test", "password": GOOD + "x"}).json()
    assert me["home"] == "/app" and me["company"]["name"] == "Haven Builders Pvt"
    assert c.get("/api/projects").status_code == 200
    me = c.post("/api/auth/login", json={"identifier": "dev@setup.test", "password": GOOD}).json()
    assert me["home"] == "/console"
