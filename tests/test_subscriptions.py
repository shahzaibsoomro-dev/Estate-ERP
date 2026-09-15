"""Super admin console, subscriptions, read-only on expiry, support mode."""
from datetime import date, timedelta

from conftest import EMAILS, login


def test_console_overview_and_companies(as_role):
    sa = as_role("superadmin")
    ov = sa.get("/api/console/overview").json()
    assert ov["companies"] >= 2 and ov["plans"]
    companies = sa.get("/api/console/companies").json()
    assert {"Haven Builders", "Beta Builders"} <= {c["name"] for c in companies}
    assert all("db_path" not in c for c in companies)


def test_create_company_with_admin(as_role):
    sa = as_role("superadmin")
    plan = sa.get("/api/console/plans").json()[0]
    r = sa.post("/api/console/companies", json={
        "name": "Gamma Estates", "plan_id": plan["id"], "admin_name": "Gamma Owner",
        "admin_email": "owner@gamma.test", "contact_phone": "0300-1234567", "trial_days": 14})
    assert r.status_code == 200, r.text
    temp = r.json()["temporary_password"]
    owner = as_role(None)
    me = login(owner, "owner@gamma.test", temp)
    assert me["role"] == "admin" and me["company"]["name"] == "Gamma Estates"
    owner.post("/api/auth/change-password", json={"current_password": temp, "new_password": "Quartz-Lamp-4821"})
    assert owner.get("/api/projects").json() == []
    sub = owner.get("/api/company/subscription").json()
    assert sub["state"]["state"] == "trial" and sub["subscription"]["plan_name"] == plan["name"]


def test_payment_extends_period_and_void_rolls_back(as_role, world):
    sa = as_role("superadmin")
    cid = world["company_b"]["id"]
    before = sa.get(f"/api/console/companies/{cid}").json()["subscription"]["current_period_end"]
    p = sa.post(f"/api/console/companies/{cid}/payments", json={
        "amount": 75000, "paid_on": date.today().isoformat(), "method": "Bank transfer", "periods": 2})
    assert p.status_code == 200, p.text
    after = sa.get(f"/api/console/companies/{cid}").json()
    assert after["subscription"]["current_period_end"] > before
    assert after["state"]["state"] == "active"  # trial converted to paid
    assert after["payments"][0]["receipt_no"].startswith("SUB-")
    # Admin of that company sees the payment; the other company does not.
    assert as_role("admin_b").get("/api/company/subscription").json()["payments"][0]["amount"] == 75000
    assert all(x["amount"] != 75000 or x["paid_on"] != date.today().isoformat()
               for x in as_role("admin").get("/api/company/subscription").json()["payments"])
    v = sa.post(f"/api/console/payments/{p.json()['id']}/void", json={"reason": "Bounced cheque"})
    assert v.status_code == 200
    assert sa.get(f"/api/console/companies/{cid}").json()["subscription"]["current_period_end"] < after["subscription"]["current_period_end"]
    assert sa.post(f"/api/console/companies/{cid}/payments", json={
        "amount": 0, "paid_on": date.today().isoformat(), "method": "Cash"}).status_code == 422


def _set_end(sa, cid, days_from_today, grace=7):
    end = (date.today() + timedelta(days=days_from_today)).isoformat()
    r = sa.put(f"/api/console/companies/{cid}/subscription", json={"current_period_end": end, "grace_days": grace})
    assert r.status_code == 200, r.text


def test_grace_then_read_only(as_role, world):
    sa = as_role("superadmin")
    cid = world["company_b"]["id"]
    admin_b = as_role("admin_b")
    _set_end(sa, cid, -3)  # within 7-day grace
    me = admin_b.get("/api/auth/me").json()
    assert me["subscription"]["state"] == "grace" and me["subscription"]["warn"]
    assert admin_b.post("/api/customers", json={"name": "Grace Buyer", "cnic": "22222-2222222-9"}).status_code == 200
    _set_end(sa, cid, -30)  # past grace → read-only
    assert admin_b.get("/api/customers").status_code == 200
    r = admin_b.post("/api/customers", json={"name": "Blocked", "cnic": "33333-3333333-3"})
    assert r.status_code == 402 and r.json()["detail"] == "subscription_expired"
    # Read-only previews still work; customers' portal keeps working.
    assert as_role("customer_b").get("/api/me/overview").status_code == 200
    _set_end(sa, cid, 30)
    assert admin_b.post("/api/customers", json={"name": "Back Again", "cnic": "44444-4444444-4"}).status_code == 200


def test_suspend_blocks_staff_but_not_customers(as_role, world):
    sa = as_role("superadmin")
    cid = world["company_b"]["id"]
    admin_b = as_role("admin_b")
    assert sa.patch(f"/api/console/companies/{cid}", json={"status": "suspended"}).status_code == 200
    assert admin_b.get("/api/auth/me").status_code == 401  # sessions revoked
    r = as_role(None).post("/api/auth/login", json={"identifier": EMAILS["admin_b"], "password": "Str0ng-Test-Pass"})
    assert r.status_code == 403 and "suspended" in r.json()["detail"]
    assert as_role("customer_b").get("/api/me/overview").status_code == 200
    assert sa.patch(f"/api/console/companies/{cid}", json={"status": "active"}).status_code == 200
    login(as_role(None), EMAILS["admin_b"])


def test_support_mode(as_role, world):
    sa = as_role("superadmin")
    cid = world["company_b"]["id"]
    assert sa.get("/api/customers").status_code == 403
    assert sa.post(f"/api/console/companies/{cid}/support").json()["home"] == "/app"
    me = sa.get("/api/auth/me").json()
    assert me["support_mode"] and me["company"]["id"] == cid and me["home"] == "/app"
    assert "Beta Buyer" in {c["name"] for c in sa.get("/api/customers").json()}
    assert sa.get("/api/company/employees").status_code == 200
    # The company admin can see that support accessed their account.
    acts = [a["action"] for a in as_role("admin_b").get("/api/company/activity").json()]
    assert "support.enter" in acts
    assert sa.post("/api/auth/exit-support").json()["home"] == "/console"
    assert sa.get("/api/customers").status_code == 403


def test_superadmin_recovers_admin(as_role, world):
    sa = as_role("superadmin")
    uid = world["ids"]["admin_b"]
    temp = sa.post(f"/api/console/users/{uid}/reset-password").json()["temporary_password"]
    c = as_role(None)
    assert login(c, EMAILS["admin_b"], temp)["must_change_password"]
    c.post("/api/auth/change-password", json={"current_password": temp, "new_password": "Str0ng-Test-Pass-2"})
    # restore the fixture password
    from backend.auth.passwords import hash_password
    from backend.database import platform_db
    with platform_db() as conn:
        conn.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password("Str0ng-Test-Pass"), uid))
    assert sa.post(f"/api/console/users/{world['ids']['superadmin']}/reset-password").status_code == 404
    assert as_role("admin").post(f"/api/console/users/{uid}/reset-password").status_code == 403


def test_plan_limits(as_role):
    sa = as_role("superadmin")
    plan = sa.post("/api/console/plans", json={"name": "Tiny", "price_monthly": 1000, "max_employees": 1,
                                               "max_projects": 1}).json()
    r = sa.post("/api/console/companies", json={"name": "Tiny Co", "plan_id": plan["id"],
                                                "admin_name": "Tiny", "admin_email": "tiny@test.local"}).json()
    owner = as_role(None)
    login(owner, "tiny@test.local", r["temporary_password"])
    owner.post("/api/auth/change-password", json={"current_password": r["temporary_password"],
                                                  "new_password": "Quartz-Lamp-4822"})
    body = {"name": "E1", "email": "e1@tiny.test", "permissions": {}, "all_projects": True}
    assert owner.post("/api/company/employees", json=body).status_code == 200
    r2 = owner.post("/api/company/employees", json={**body, "email": "e2@tiny.test"})
    assert r2.status_code == 400 and "plan allows 1" in r2.json()["detail"]
    assert owner.post("/api/projects", json={"name": "P1", "location": "X"}).status_code == 200
    assert owner.post("/api/projects", json={"name": "P2", "location": "Y"}).status_code == 400


def test_legacy_users_are_migrated(tmp_path, monkeypatch):
    """A single-company install with users in haven.db moves them into the platform DB."""
    import shutil
    import sqlite3
    from pathlib import Path

    import backend.config as config
    import backend.database as database
    import backend.saas.schema as schema
    import backend.saas.service as saas
    root = Path(__file__).resolve().parents[1]
    legacy = tmp_path / "haven.db"
    shutil.copy(root / "db" / "haven.pre-sim.db", legacy)
    conn = sqlite3.connect(legacy)
    conn.execute("""CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, name TEXT, role TEXT, password_hash TEXT,
                    customer_id INTEGER, is_active INTEGER, must_change_password INTEGER, last_login_at TEXT,
                    password_changed_at TEXT, created_at TEXT)""")
    conn.execute("INSERT INTO users VALUES(1,'old-sa@x.test','Old SA','superadmin','scrypt$x',NULL,1,0,NULL,NULL,'2026-01-01')")
    conn.execute("INSERT INTO users VALUES(2,'old-admin@x.test','Old Admin','admin','scrypt$y',NULL,1,0,NULL,NULL,'2026-01-01')")
    conn.commit()
    conn.close()
    platform = tmp_path / "platform.db"
    for mod in (config, database, saas):
        monkeypatch.setattr(mod, "DB_PATH", str(legacy), raising=False)
    monkeypatch.setattr(database, "PLATFORM_DB_PATH", str(platform))
    monkeypatch.setattr(schema, "PLATFORM_DB_PATH", str(platform))
    import backend.db.seed as seed
    monkeypatch.setattr(seed, "DB_PATH", str(legacy))
    saas.bootstrap_platform()
    p = sqlite3.connect(platform)
    rows = p.execute("SELECT email, role, company_id FROM users ORDER BY id").fetchall()
    assert rows == [("old-sa@x.test", "superadmin", None), ("old-admin@x.test", "admin", 1)]
    assert p.execute("SELECT COUNT(*) FROM companies").fetchone()[0] == 1
