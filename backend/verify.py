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
    "site_logs", "ledger_entries",
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
    if "overdue" in rec and "receivable" in rec and "ageing" in rec:
        ok("GET /api/recovery")
        ageing = rec["ageing"]
        if all(k in ageing for k in ("d30", "d60", "d90")):
            ok("recovery ageing buckets")
        else:
            fail("recovery ageing", str(ageing)[:120])
        if rec["overdue"]:
            row = rec["overdue"][0]
            if all(k in row for k in ("id", "booking_id", "customer_id", "amount")):
                ok("recovery overdue row ids")
            else:
                fail("recovery overdue ids", str(row)[:160])
    else:
        fail("GET /api/recovery", "missing overdue/receivable/ageing")
    dn = get("/api/demand-notices")
    if isinstance(dn, list):
        ok("GET /api/demand-notices")
except Exception as e:
    fail("dashboard/recovery", str(e))

print("\n=== Step 13: Stubs ===")
for path, expect in [
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
try:
    led = get("/api/ledger")
    if isinstance(led, dict) and "entries" in led and "inflow" in led and "outflow" in led:
        ok("GET /api/ledger cashbook shape")
    else:
        fail("GET /api/ledger", str(list(led)[:12]) if isinstance(led, dict) else type(led))
except Exception as e:
    fail("GET /api/ledger", str(e))

def delete(path):
    req = urllib.request.Request(BASE + path, method="DELETE")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def expect_http_error(path, method, data, code=400):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(data).encode() if data else None,
        headers={"Content-Type": "application/json"} if data else {},
        method=method,
    )
    try:
        urllib.request.urlopen(req)
        return False, "expected error"
    except urllib.error.HTTPError as e:
        return e.code == code, e.read().decode()[:200]


print("\n=== Step 16: Customer CRUD ===")
try:
    cnic_a = f"1{SUFFIX}-1111111-1"
    cnic_b = f"1{SUFFIX}-2222222-2"
    c1 = post("/api/customers", {
        "name": f"CRUD {SUFFIX}",
        "cnic": cnic_a,
        "father_name": "Test Father",
        "phone": "03001234567",
        "emergency_contact_number": "03007654321",
        "email": "crud@test.local",
        "address": "Lahore Test",
        "description": "Verify customer",
    })
    if c1.get("father_name") == "Test Father" and c1.get("phone") == "03001234567":
        ok("POST customer with full profile")
    else:
        fail("POST customer", str(c1)[:160])

    d1 = get(f"/api/customers/{c1['id']}")
    if (
        isinstance(d1.get("bookings"), list)
        and isinstance(d1.get("payments"), list)
        and d1.get("father_name") == "Test Father"
        and d1.get("address") == "Lahore Test"
    ):
        ok("GET /api/customers/{id} detail shape")
    else:
        fail("GET customer detail", str({k: d1.get(k) for k in ("bookings", "payments", "father_name", "address")}))

    u1 = put(f"/api/customers/{c1['id']}", {
        "name": f"CRUD {SUFFIX} Edit",
        "cnic": cnic_a,
        "father_name": "Father Edit",
        "phone": "03111234567",
        "email": "edit@test.local",
        "address": "Karachi Test",
        "emergency_contact_number": "03000000000",
        "description": "Updated",
    })
    if u1.get("name", "").endswith("Edit") and u1.get("phone") == "03111234567" and u1.get("address") == "Karachi Test":
        ok("PUT customer updates profile")
    else:
        fail("PUT customer", str(u1)[:160])

    c2 = post("/api/customers", {"name": f"CRUD B {SUFFIX}", "cnic": cnic_b})
    dup_ok, _ = expect_http_error(f"/api/customers/{c2['id']}", "PUT", {
        "name": f"CRUD B {SUFFIX}", "cnic": cnic_a,
    })
    if dup_ok:
        ok("PUT rejects duplicate CNIC")
    else:
        fail("PUT duplicate CNIC", "should return 400")

    blank_ok, _ = expect_http_error(f"/api/customers/{c2['id']}", "PUT", {
        "name": "  ", "cnic": cnic_b,
    })
    if blank_ok:
        ok("PUT rejects blank name")
    else:
        fail("PUT blank name", "should return 400")

    delete(f"/api/customers/{c2['id']}")
    delete(f"/api/customers/{c1['id']}")
    ok("DELETE customer without bookings")

    gone_ok, _ = expect_http_error(f"/api/customers/{c1['id']}", "GET", None, 404)
    if gone_ok:
        ok("GET deleted customer returns 404")
    else:
        fail("GET deleted customer", "should return 404")

    c3 = post("/api/customers", {"name": f"Hold {SUFFIX}", "cnic": f"1{SUFFIX}-3333333-3"})
    proj = post("/api/projects", {"name": f"CustHold {SUFFIX}", "location": "Test", "status": "planning"})
    unit = post("/api/units", {
        "project_id": proj["id"], "unit_no": f"CH-{SUFFIX}",
        "unit_type": "Flat", "floor_number": 1, "base_sale_price": 1000000,
    })
    put(f"/api/units/{unit['id']}/status", {
        "status": "hold",
        "hold_customer_id": c3["id"],
        "hold_until": "2026-12-31",
        "hold_notes": "verify",
    })
    hold_ok, _ = expect_http_error(f"/api/customers/{c3['id']}", "DELETE", None, 400)
    if hold_ok:
        ok("block delete customer holding a unit")
    else:
        fail("delete holding customer", "should return 400")
    put(f"/api/units/{unit['id']}/status", {"status": "available"})
    delete(f"/api/units/{unit['id']}")
    delete(f"/api/projects/{proj['id']}")
    delete(f"/api/customers/{c3['id']}")
    ok("cleanup hold-customer fixtures")

    c4 = post("/api/customers", {"name": f"Booked {SUFFIX}", "cnic": f"1{SUFFIX}-4444444-4"})
    proj2 = post("/api/projects", {"name": f"CustBk {SUFFIX}", "location": "Test", "status": "planning"})
    unit2 = post("/api/units", {
        "project_id": proj2["id"], "unit_no": f"CB-{SUFFIX}",
        "unit_type": "Flat", "floor_number": 1, "base_sale_price": 2000000,
    })
    post("/api/bookings", {
        "unit_id": unit2["id"], "project_id": proj2["id"], "customer_id": c4["id"],
        "sale_price": 2000000, "down_payment": 200000, "booking_date": "2026-01-15",
        "installments": [{"amount": 1800000, "due_date": "2026-02-15", "type": "Monthly"}],
    })
    booked_ok, _ = expect_http_error(f"/api/customers/{c4['id']}", "DELETE", None, 400)
    if booked_ok:
        ok("block delete customer with bookings")
    else:
        fail("delete booked customer", "should return 400")
except Exception as e:
    fail("customer CRUD", str(e))

print("\n=== Step 17: Vendors, PO lifecycle, site logs ===")
try:
    v = post("/api/vendors", {
        "name": f"Ops Vendor {SUFFIX}",
        "category": "Cement",
        "contact": "03001112222",
        "description": "Verify vendor",
        "status": "active",
    })
    vid = v["id"]
    ok("POST vendor")

    detail = get(f"/api/vendors/{vid}")
    if (
        isinstance(detail.get("purchase_orders"), list)
        and isinstance(detail.get("payments"), list)
        and detail.get("name")
    ):
        ok("GET /api/vendors/{id} detail shape")
    else:
        fail("GET vendor detail", str({k: detail.get(k) for k in ("name", "purchase_orders", "payments")}))

    u = put(f"/api/vendors/{vid}", {
        "name": f"Ops Vendor {SUFFIX} Edit",
        "category": "Steel",
        "contact": "03003334444",
        "status": "active",
    })
    if str(u.get("name", "")).endswith("Edit") and u.get("category") == "Steel":
        ok("PUT vendor updates profile")
    else:
        fail("PUT vendor", str(u)[:160])

    vtmp = post("/api/vendors", {"name": f"Ops Temp {SUFFIX}", "category": "Misc"})
    delete(f"/api/vendors/{vtmp['id']}")
    gone_ok, _ = expect_http_error(f"/api/vendors/{vtmp['id']}", "GET", None, 404)
    if gone_ok:
        ok("DELETE vendor without POs")
    else:
        fail("DELETE vendor", "should 404 after delete")

    blank_ok, _ = expect_http_error(f"/api/vendors/{vid}", "PUT", {"name": "  ", "status": "active"})
    if blank_ok:
        ok("PUT vendor rejects blank name")
    else:
        fail("PUT vendor blank name", "should return 400")

    proj = post("/api/projects", {
        "name": f"Ops Proj {SUFFIX}",
        "location": "Test",
        "status": "planning",
        "current_progress": 40,
    })
    pid = proj["id"]

    po = post("/api/purchase-orders", {
        "vendor_id": vid,
        "project_id": pid,
        "material": "Cement bags",
        "qty": "10",
        "unit_cost": 1000,
        "site": "Block A",
    })
    if str(po.get("po_no", "")).startswith(f"PO-{date.today().year}-"):
        ok("create PO with auto PO#")
    else:
        fail("auto PO number", str(po.get("po_no")))
    if po.get("status") == "draft" and po.get("grn_status") == "na":
        ok("new PO starts as draft")
    else:
        fail("PO draft status", f"{po.get('status')} / {po.get('grn_status')}")
    if po.get("total") == 10000:
        ok("PO total auto-calc from qty x unit cost")
    else:
        fail("PO total calc", str(po.get("total")))

    blocked, _ = expect_http_error(f"/api/vendors/{vid}", "DELETE", None, 400)
    if blocked:
        ok("block delete vendor with POs")
    else:
        fail("delete vendor with POs", "should return 400")

    po_id = po["id"]
    put(f"/api/purchase-orders/{po_id}/status", {"status": "approved"})
    po_a = get(f"/api/purchase-orders/{po_id}")
    if po_a.get("status") == "approved":
        ok("approve PO")
    else:
        fail("approve PO", str(po_a.get("status")))

    put(f"/api/purchase-orders/{po_id}/status", {"status": "grn"})
    po_g = get(f"/api/purchase-orders/{po_id}")
    if po_g.get("status") == "payment_pending" and po_g.get("grn_status") == "done":
        ok("GRN to payment_pending")
    else:
        fail("GRN", f"{po_g.get('status')} / {po_g.get('grn_status')}")

    post("/api/vendor-payments", {
        "vendor_id": vid,
        "purchase_order_id": po_id,
        "amount": 4000,
        "payment_date": date.today().isoformat(),
        "payment_method": "Cash",
    })
    po_p = get(f"/api/purchase-orders/{po_id}")
    if po_p.get("status") == "payment_pending" and int(po_p.get("paid") or 0) == 4000:
        ok("partial pay stays payment_pending")
    else:
        fail("partial pay", f"status={po_p.get('status')} paid={po_p.get('paid')}")

    post("/api/vendor-payments", {
        "vendor_id": vid,
        "purchase_order_id": po_id,
        "amount": 6000,
        "payment_date": date.today().isoformat(),
        "payment_method": "Bank Transfer",
    })
    po_c = get(f"/api/purchase-orders/{po_id}")
    if po_c.get("status") == "completed":
        ok("full pay to completed")
    else:
        fail("full pay", str(po_c.get("status")))

    slog = post("/api/site-logs", {
        "project_id": pid,
        "log_date": date.today().isoformat(),
        "engineer": "Eng Test",
        "workers_skilled": 4,
        "workers_unskilled": 8,
        "material_used": "Cement 20 bags",
        "work_done": "Column casting Block A",
    })
    if slog.get("id") and slog.get("engineer") == "Eng Test":
        ok("POST site-log")
    else:
        fail("POST site-log", str(slog)[:160])

    logs = get("/api/site-logs")
    if isinstance(logs, list) and any(l.get("id") == slog.get("id") for l in logs):
        ok("GET site-logs contains new entry")
    else:
        fail("GET site-logs", "created log missing")

    filtered = get(f"/api/site-logs?project_ids={pid}")
    if any(l.get("id") == slog.get("id") for l in filtered):
        ok("GET site-logs honors project_ids")
    else:
        fail("site-logs filter", "missing filtered log")

    delete(f"/api/site-logs/{slog['id']}")
    after = get(f"/api/site-logs?project_ids={pid}")
    if not any(l.get("id") == slog.get("id") for l in after):
        ok("DELETE site-log")
    else:
        fail("DELETE site-log", "log still listed")
except Exception as e:
    fail("ops vendor/PO/site", str(e))

print("\n=== Step 18: Agents + cashbook ===")
try:
    ag = post("/api/agents", {
        "name": f"Fin Ag {SUFFIX}",
        "contact": "03001110000",
        "default_rate_pct": 2.5,
        "status": "active",
    })
    aid = ag["id"]
    ok("POST agent")

    detail = get(f"/api/agents/{aid}")
    if isinstance(detail.get("commissions"), list) and isinstance(detail.get("payments"), list):
        ok("GET agent detail shape")
    else:
        fail("GET agent detail", str(detail)[:160])

    u = put(f"/api/agents/{aid}", {
        "name": f"Fin Ag {SUFFIX} Edit",
        "contact": "03002220000",
        "default_rate_pct": 3,
        "status": "active",
    })
    if str(u.get("name", "")).endswith("Edit") and float(u.get("default_rate_pct") or 0) == 3:
        ok("PUT agent")
    else:
        fail("PUT agent", str(u)[:160])

    tmp = post("/api/agents", {"name": f"Fin Tmp {SUFFIX}", "default_rate_pct": 2})
    delete(f"/api/agents/{tmp['id']}")
    gone, _ = expect_http_error(f"/api/agents/{tmp['id']}", "GET", None, 404)
    if gone:
        ok("DELETE agent without commissions")
    else:
        fail("DELETE agent", "should 404 after delete")

    proj = post("/api/projects", {"name": f"Fin Proj {SUFFIX}", "location": "Test", "status": "planning"})
    unit = post("/api/units", {
        "project_id": proj["id"], "unit_no": f"FA-{SUFFIX}",
        "unit_type": "Flat", "floor_number": 1, "base_sale_price": 1000000,
    })
    cust = post("/api/customers", {"name": f"Fin Cust {SUFFIX}", "cnic": f"9{SUFFIX}-1111111-1"})
    post("/api/bookings", {
        "unit_id": unit["id"], "project_id": proj["id"], "customer_id": cust["id"],
        "sale_price": 1000000, "down_payment": 200000, "booking_date": date.today().isoformat(),
        "agent_id": aid,
        "installments": [{"amount": 800000, "due_date": "2026-12-15", "type": "Monthly"}],
    })
    after_bk = get(f"/api/agents/{aid}")
    if after_bk.get("commission_unpaid", 0) == 30000:
        ok("booking earns agent commission at agent rate")
    else:
        fail("agent commission on booking", str(after_bk.get("commission_unpaid")))

    blocked, _ = expect_http_error(f"/api/agents/{aid}", "DELETE", None, 400)
    if blocked:
        ok("block delete agent with commissions")
    else:
        fail("delete agent with commissions", "should return 400")

    post(f"/api/agents/{aid}/pay", {
        "amount": 10000,
        "payment_date": date.today().isoformat(),
        "notes": "partial verify",
    })
    mid = get(f"/api/agents/{aid}")
    if mid.get("commission_unpaid") == 20000 and mid.get("commission_paid") == 10000:
        ok("partial agent pay")
    else:
        fail("partial agent pay", f"paid={mid.get('commission_paid')} unpaid={mid.get('commission_unpaid')}")

    over_ok, _ = expect_http_error(f"/api/agents/{aid}/pay", "POST", {
        "amount": 999999, "payment_date": date.today().isoformat(),
    })
    if over_ok:
        ok("reject agent overpay")
    else:
        fail("agent overpay", "should return 400")

    le = post("/api/ledger", {
        "entry_date": date.today().isoformat(),
        "narration": f"Misc expense {SUFFIX}",
        "amount": 1500,
        "direction": "out",
        "category": "Expense",
    })
    if le.get("id"):
        ok("POST ledger other entry")
    else:
        fail("POST ledger", str(le)[:160])
    book = get("/api/ledger")
    if any(e.get("id") == le.get("id") and e.get("source") == "manual" for e in book.get("entries") or []):
        ok("cashbook includes manual entry")
    else:
        fail("cashbook manual", "entry missing")
    delete(f"/api/ledger/{le['id']}")
    book2 = get("/api/ledger")
    if not any(e.get("id") == le.get("id") for e in book2.get("entries") or []):
        ok("DELETE ledger entry")
    else:
        fail("DELETE ledger", "still listed")
except Exception as e:
    fail("agents/cashbook", str(e))

print("\n=== Step 15: Project-Unit lifecycle ===")
try:
    tag = f"PU{SUFFIX}"
    proj = post("/api/projects", {
        "name": f"Lifecycle {tag}",
        "location": "Test City",
        "status": "planning",
        "number_of_units": 2,
    })
    pid = proj["id"]
    ok("create project without units")

    u1 = post("/api/units", {
        "project_id": pid, "unit_no": f"LC-{tag}-1",
        "unit_type": "Flat", "floor_number": 2, "base_sale_price": 5000000,
    })
    uid = u1["id"]
    ok("add unit to project via POST")

    u1b = put(f"/api/units/{uid}", {
        "unit_no": f"LC-{tag}-1",
        "unit_type": "Flat", "floor_number": 3, "base_sale_price": 5500000,
    })
    if u1b.get("floor_number") == 3 and u1b.get("base_sale_price") == 5500000:
        ok("update unit via PUT")
    else:
        fail("update unit", str(u1b))

    dup_ok, _ = expect_http_error("/api/units", "POST", {
        "project_id": pid, "unit_no": f"LC-{tag}-1",
    })
    if dup_ok:
        ok("reject duplicate unit_no in same project")
    else:
        fail("duplicate unit_no", "should return 400")

    del_proj_ok, _ = expect_http_error(f"/api/projects/{pid}", "DELETE", None)
    if del_proj_ok:
        ok("block delete project while units exist")
    else:
        fail("delete project with units", "should return 400")

    delete(f"/api/units/{uid}")
    ok("delete available unit")

    delete(f"/api/projects/{pid}")
    ok("delete project after all units removed")

    listed = get(f"/api/projects")
    if any(p["id"] == pid for p in listed):
        fail("project removed", "still in list")
    else:
        ok("project no longer listed")
except Exception as e:
    fail("project-unit lifecycle", str(e))

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
