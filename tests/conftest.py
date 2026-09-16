import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Isolated copies: a platform DB, the sample company DB, and a tenants folder.
_tmp = tempfile.mkdtemp(prefix="erp-test-")
_src = ROOT / "db" / "haven.pre-sim.db"
if not _src.exists():
    _src = ROOT / "db" / "haven.db"
shutil.copy(_src, os.path.join(_tmp, "haven.db"))
os.environ["ERP_DB_PATH"] = os.path.join(_tmp, "haven.db")
os.environ["ERP_PLATFORM_DB_PATH"] = os.path.join(_tmp, "platform.db")
os.environ["ERP_TENANTS_DIR"] = os.path.join(_tmp, "tenants")
os.environ.setdefault("ERP_LOGIN_MAX_FAILS_PER_IP", "1000")

from fastapi.testclient import TestClient  # noqa: E402

from backend.auth import service  # noqa: E402
from backend.auth.permissions import preset_permissions  # noqa: E402
from backend.database import fetch_one, get_db, platform_db  # noqa: E402
from backend.main import app  # noqa: E402
from backend.saas import service as saas  # noqa: E402

PASSWORD = "Str0ng-Test-Pass"
EMAILS = {
    "superadmin": "sa@test.local",
    "admin": "admin@test.local",
    "admin_b": "admin-b@test.local",
    "employee_all": "emp-all@test.local",
    "employee_scoped": "emp-scoped@test.local",
    "customer": "cust@test.local",
    "customer2": "cust2@test.local",
    "customer_b": "cust-b@test.local",
}


@pytest.fixture(scope="session")
def world():
    """Two companies with users of every role."""
    with TestClient(app):  # startup: platform bootstrap + migrations
        pass
    with platform_db() as pc:
        company_a = fetch_one(pc, "SELECT * FROM companies ORDER BY id LIMIT 1")
        plan = fetch_one(pc, "SELECT id FROM plans WHERE code='enterprise'")
        company_b = saas.create_company(pc, name="Beta Builders", plan_id=plan["id"], trial_days=30)
    a_db = saas.resolve_db_path(company_a["db_path"])
    b_db = saas.resolve_db_path(company_b["db_path"])
    with get_db(a_db) as conn:
        rows = conn.execute(
            """SELECT c.id, c.cnic, b.project_id FROM customers c JOIN bookings b ON b.customer_id=c.id AND b.status='active'
               GROUP BY c.id ORDER BY c.id"""
        ).fetchall()
        projects = [r[0] for r in conn.execute("SELECT id FROM projects ORDER BY id")]
    cust1 = rows[0]
    cust2 = next(r for r in rows if r[2] != cust1[2])  # a customer in a different project
    scoped_project = cust1[2]
    with get_db(b_db) as conn:
        conn.execute("INSERT INTO customers(name, cnic) VALUES('Beta Buyer', '11111-1111111-1')")
        b_cust = conn.execute("SELECT id FROM customers").fetchone()[0]
        conn.execute("INSERT INTO projects(name, location) VALUES('Beta Towers', 'Karachi')")

    def mk(role, key, cid, **kw):
        with platform_db() as pc:
            u, _ = service.create_user(pc, email=EMAILS[key], name=key.title(), role=role, company_id=cid,
                                       password=PASSWORD, must_change_password=False, **kw)
            return u["id"]

    ids = {
        "superadmin": mk("superadmin", "superadmin", None),
        "admin": mk("admin", "admin", company_a["id"]),
        "admin_b": mk("admin", "admin_b", company_b["id"]),
        "employee_all": mk("employee", "employee_all", company_a["id"]),
        "employee_scoped": mk("employee", "employee_scoped", company_a["id"]),
        "customer": mk("customer", "customer", company_a["id"], customer_id=cust1[0], customer_cnic=cust1[1]),
        "customer2": mk("customer", "customer2", company_a["id"], customer_id=cust2[0], customer_cnic=cust2[1]),
        "customer_b": mk("customer", "customer_b", company_b["id"], customer_id=b_cust),
    }
    with platform_db() as pc:
        service.set_employee_access(pc, ids["employee_all"], permissions=preset_permissions("viewer"),
                                    all_projects=True, project_ids=[])
        service.set_employee_access(pc, ids["employee_scoped"], permissions=preset_permissions("sales"),
                                    all_projects=False, project_ids=[scoped_project])
    return {
        "ids": ids, "company_a": company_a, "company_b": company_b, "a_db": a_db, "b_db": b_db,
        "cust1": cust1[0], "cust2": cust2[0], "scoped_project": scoped_project, "other_project": cust2[2],
        "projects": projects,
    }


def login(client, email, password=PASSWORD):
    r = client.post("/api/auth/login", json={"identifier": email, "password": password})
    assert r.status_code == 200, r.text
    client.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    return r.json()


@pytest.fixture
def as_role(world):
    clients = []

    def make(role):
        c = TestClient(app)
        clients.append(c)
        if role:
            login(c, EMAILS[role])
        return c
    yield make
    for c in clients:
        c.close()
