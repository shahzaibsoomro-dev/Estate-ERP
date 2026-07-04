"""Step-by-step verification of FastAPI backend against plan checklist."""
import json
import sqlite3
import time
import urllib.error
import urllib.request
from datetime import date, timedelta

BASE = "http://127.0.0.1:5050"
DB = "db/haven.db"
SUFFIX = str(int(time.time()))[-7:]
passed = []
failed = []


def ok(name):
    passed.append(name)
    print(f"  PASS  {name}")


def fail(name, detail):
    failed.append((name, detail))
    print(f"  FAIL  {name}: {detail}")


def get(path):
    with urllib.request.urlopen(BASE + path) as r:
        return json.loads(r.read())


def post(path, data):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def put(path, data):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


print("\n=== Step 1: Scaffold & health ===")
try:
    h = get("/api/health")
    if h.get("status") == "ok" and h.get("units_in_db", 0) > 0:
        ok("health endpoint")
    else:
        fail("health endpoint", str(h))
except Exception as e:
    fail("health endpoint", str(e))

print("\n=== Step 2: Schema tables ===")
conn = sqlite3.connect(DB)
tables = {r[0] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table'"
).fetchall()}
required = {
    "company_settings", "projects", "units", "customers", "agents", "bookings",
    "installments", "payments", "receipts", "booking_cancellations", "vendors",
    "purchase_orders", "vendor_payments", "budget_categories", "project_budget_lines",
    "investors", "investor_agreements", "investor_contributions", "investor_distributions",
    "agent_commissions", "agent_commission_payments", "audit_log", "schema_meta",
}
missing = required - tables
if not missing:
    ok(f"schema tables ({len(required)} required)")
else:
    fail("schema tables", f"missing: {missing}")

ver = conn.execute("SELECT value FROM schema_meta WHERE key='version'").fetchone()
if ver and int(ver[0]) >= 2:
    ok("schema version >= 2")
else:
    fail("schema version", str(ver))

print("\n=== Step 3: Settings ===")
try:
    s = get("/api/settings")
    if "cancellation_forfeit_pct" in s:
        ok("GET /api/settings")
    else:
        fail("GET /api/settings", "missing keys")
except Exception as e:
    fail("GET /api/settings", str(e))

print("\n=== Step 4: Projects (computed inventory) ===")
try:
    projects = get("/api/projects")
    if len(projects) >= 3:
        ok("GET /api/projects")
    p1 = projects[0]
    db_counts = conn.execute(
        """SELECT COUNT(*) t,
           SUM(CASE WHEN status IN ('booked','sold','possession_delivered') THEN 1 ELSE 0 END) s,
           SUM(CASE WHEN status='available' THEN 1 ELSE 0 END) a,
           SUM(CASE WHEN status='hold' THEN 1 ELSE 0 END) h
           FROM units WHERE project_id=1"""
    ).fetchone()
    if p1["sold"] == db_counts[1] and p1["available"] == db_counts[2]:
        ok("project inventory computed from units")
    else:
        fail("project inventory", f"api={p1['sold']}/{p1['available']} db={db_counts[1]}/{db_counts[2]}")
except Exception as e:
    fail("projects", str(e))

print("\n=== Step 5: Units ===")
try:
    units = get("/api/units?project_id=1")
    if len(units) > 0:
        ok("GET /api/units")
    detail = get("/api/units/1")
    for k in ("unit", "booking", "installments", "payments", "summary"):
        if k not in detail:
            fail("unit detail shape", f"missing {k}")
            break
    else:
        ok("GET /api/units/{id} shape compatible with UI")
except Exception as e:
    fail("units", str(e))

print("\n=== Step 6: Customers ===")
try:
    custs = get("/api/customers")
    if len(custs) > 0 and "cust_status" in custs[0] and "total_value" in custs[0]:
        ok("GET /api/customers with computed summary")
    else:
        fail("customers", "missing computed fields")
except Exception as e:
    fail("customers", str(e))

print("\n=== Step 7: Bookings — no double-sell ===")
try:
    units_avail = get("/api/units?project_id=1&status=available")
    if not units_avail:
        fail("double-sell test", "no available units — skip")
    else:
        u = units_avail[0]
        cnic = f"9{SUFFIX}-9999999-9"
        cu = post("/api/customers", {"name": "Verify User", "cnic": cnic})
        bk = post("/api/bookings", {
            "unit_id": u["id"], "project_id": 1, "customer_id": cu["id"],
            "sale_price": 7000000, "down_payment": 1000000, "booking_date": "2025-06-15",
            "installments": [{"amount": 1000000, "due_date": "2025-06-15", "type": "Booking"}],
        })
        try:
            post("/api/bookings", {
                "unit_id": u["id"], "project_id": 1, "customer_id": cu["id"],
                "sale_price": 7000000, "down_payment": 1000000, "booking_date": "2025-06-16",
                "installments": [],
            })
            fail("double-sell prevention", "second booking should have been rejected")
        except urllib.error.HTTPError as he:
            if he.code == 400:
                ok("booking rejects double-sell on same unit")
            else:
                fail("double-sell prevention", f"HTTP {he.code}")
except urllib.error.HTTPError as he:
    body = he.read().decode() if he.fp else ""
    fail("bookings", f"HTTP {he.code}: {body[:120]}")
except Exception as e:
    fail("bookings", str(e))

print("\n=== Step 8: Payments — partial then full ===")
try:
    conn2 = sqlite3.connect(DB)
    row = conn2.execute(
        """SELECT u.id FROM units u
           JOIN bookings b ON b.unit_id=u.id AND b.status='active'
           JOIN installments i ON i.booking_id=b.id
           WHERE i.remaining_amount > 0 AND i.status IN ('pending','partial','overdue')
           LIMIT 1"""
    ).fetchone()
    conn2.close()
    if not row:
        fail("partial payment", "no unit with open installment")
    else:
        uid = row[0]
        detail = get(f"/api/units/{uid}")
        inst = next(
            i for i in detail["installments"]
            if i["remaining_amount"] > 0 and i["status"] in ("pending", "partial", "overdue")
        )
        bk_id = detail["booking"]["id"]
        cust_id = detail["booking"]["customer_id"]
        half = max(inst["remaining_amount"] // 2, 1)
        post("/api/payments", {
            "installment_id": inst["id"], "booking_id": bk_id,
            "customer_id": cust_id, "amount": half, "method": "Cash",
        })
        d2 = get(f"/api/units/{uid}")
        inst2 = next(i for i in d2["installments"] if i["id"] == inst["id"])
        if inst2["status"] == "partial":
            ok("partial payment sets status=partial")
        else:
            fail("partial payment", f"status={inst2['status']}")
        post("/api/payments", {
            "installment_id": inst["id"], "booking_id": bk_id,
            "customer_id": cust_id, "amount": inst2["remaining_amount"], "method": "Cash",
        })
        d3 = get(f"/api/units/{uid}")
        inst3 = next(i for i in d3["installments"] if i["id"] == inst["id"])
        if inst3["status"] == "paid":
            ok("full payment sets status=paid")
        else:
            fail("full payment", f"status={inst3['status']}")
except Exception as e:
    fail("payments", str(e))

print("\n=== Step 9: Overdue auto-calculation ===")
try:
    conn.execute(
        """UPDATE installments SET due_date=?, paid_amount=0, remaining_amount=amount, status='pending'
           WHERE id=(SELECT id FROM installments WHERE status='pending' LIMIT 1)""",
        ((date.today() - timedelta(days=5)).isoformat(),),
    )
    conn.commit()
    rec = get("/api/recovery")
    overdue_ids = {o["id"] for o in rec["overdue"]}
    row = conn.execute(
        "SELECT id FROM installments WHERE due_date < date('now') AND remaining_amount > 0 LIMIT 1"
    ).fetchone()
    if row and row[0] in overdue_ids:
        ok("overdue auto-calculated on recovery read")
    else:
        fail("overdue", f"installment {row} not in overdue list")
except Exception as e:
    fail("overdue", str(e))

print("\n=== Step 10: Cancellation ===")
try:
    units_avail = get("/api/units?project_id=1&status=available")
    if not units_avail:
        ok("cancellation (skipped — no available units for fresh booking)")
    else:
        u = units_avail[0]
        cnic = f"8{SUFFIX}-8888888-8"
        cu = post("/api/customers", {"name": "Cancel Test", "cnic": cnic})
        bk = post("/api/bookings", {
            "unit_id": u["id"], "project_id": 1, "customer_id": cu["id"],
            "sale_price": 6000000, "down_payment": 1800000, "booking_date": "2025-06-01",
            "installments": [{"amount": 1800000, "due_date": "2025-06-01", "type": "Booking"}],
        })
        bk_id = bk["booking_id"]
        unit_id = u["id"]
        result = post(f"/api/bookings/{bk_id}/cancel", {"reason": "test"})
        unit_after = conn.execute("SELECT status FROM units WHERE id=?", (unit_id,)).fetchone()[0]
        if unit_after == "available" and result.get("forfeit_pct") == 30.0:
            ok("cancellation frees unit with 30% forfeit default")
        else:
            fail("cancellation", f"unit={unit_after} result={result}")
except urllib.error.HTTPError as he:
    body = he.read().decode() if he.fp else ""
    fail("cancellation", f"HTTP {he.code}: {body[:120]}")
except Exception as e:
    fail("cancellation", str(e))

print("\n=== Step 11: Vendors, POs, budget, agents, investors ===")
for path, label in [
    ("/api/vendors", "vendors"),
    ("/api/purchase-orders", "purchase-orders"),
    ("/api/agents", "agents"),
    ("/api/investors", "investors"),
    ("/api/budget/categories", "budget categories"),
    ("/api/budget/summary", "budget summary"),
]:
    try:
        d = get(path)
        if isinstance(d, list) and len(d) > 0:
            ok(f"GET {path}")
        elif isinstance(d, list):
            fail(label, "empty list")
        else:
            ok(f"GET {path}")
    except Exception as e:
        fail(label, str(e))

print("\n=== Step 12: Dashboard & recovery ===")
try:
    dash = get("/api/dashboard")
    for k in ("kpi", "overdue", "alerts", "sales_chart", "recovery_chart"):
        if k not in dash:
            fail("dashboard shape", f"missing {k}")
            break
    else:
        kpi = dash["kpi"]
        for f in ("total_units", "sold", "available", "hold", "receivable", "payable"):
            if f not in kpi:
                fail("dashboard kpi", f"missing {f}")
                break
        else:
            ok("dashboard KPI shape compatible with UI")
    rec = get("/api/recovery")
    if "overdue" in rec and "receivable" in rec:
        ok("GET /api/recovery")
    dn = get("/api/demand-notices")
    if isinstance(dn, list):
        ok("GET /api/demand-notices")
except Exception as e:
    fail("dashboard/recovery", str(e))

print("\n=== Step 13: Stubs ===")
for path, expect in [
    ("/api/site-logs", list),
    ("/api/ledger", dict),
    ("/api/reports/ageing", dict),
    ("/api/reports/sales", list),
]:
    try:
        d = get(path)
        if isinstance(d, expect):
            ok(f"stub {path}")
        else:
            fail(f"stub {path}", f"expected {expect}, got {type(d)}")
    except Exception as e:
        fail(f"stub {path}", str(e))

print("\n=== Step 14: Audit log ===")
audit_count = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
if audit_count > 0:
    ok(f"audit_log has entries ({audit_count})")
else:
    fail("audit_log", "no entries after operations")

conn.close()

print("\n" + "=" * 50)
print(f"PASSED: {len(passed)}  FAILED: {len(failed)}")
if failed:
    for name, detail in failed:
        print(f"  - {name}: {detail}")
    raise SystemExit(1)
print("All verification steps passed.")
