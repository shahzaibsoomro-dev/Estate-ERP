"""E2E simulation: wipe non-Haven noise, play Gulberg Square through the APIs, report."""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

from backend.config import BASE_DIR, DB_PATH

BASE = os.environ.get("VERIFY_BASE", "http://127.0.0.1:5050")
STATE_PATH = os.path.join(BASE_DIR, "db", "simulation_state.json")
REPORT_PATH = os.path.join(BASE_DIR, "SIMULATION_REPORT.md")
BACKUP_PATH = os.path.join(BASE_DIR, "db", "haven.pre-sim.db")
TODAY = date.today().isoformat()


class ApiError(Exception):
    def __init__(self, status: int, body: str, path: str):
        super().__init__(f"HTTP {status} {path}: {body[:400]}")
        self.status = status
        self.body = body
        self.path = path


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def q(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def q1(conn, sql, params=()):
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def backup_db() -> str:
    Path(os.path.dirname(BACKUP_PATH)).mkdir(parents=True, exist_ok=True)
    if os.path.exists(BACKUP_PATH):
        return "exists"
    src = Path(DB_PATH)
    shutil.copy2(src, BACKUP_PATH)
    for suffix in ("-wal", "-shm"):
        extra = Path(str(src) + suffix)
        if extra.exists():
            shutil.copy2(extra, Path(str(BACKUP_PATH) + suffix))
    return "created"


def req(method: str, path: str, data=None):
    body = None if data is None else json.dumps(data).encode()
    headers = {"Content-Type": "application/json"} if data is not None else {}
    r = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(err)
            err = parsed.get("detail") or err
        except (json.JSONDecodeError, AttributeError):
            pass
        raise ApiError(e.code, str(err), path) from e


def get(path):
    return req("GET", path)


def post(path, data):
    return req("POST", path, data)


def put(path, data):
    return req("PUT", path, data)


def delete(path):
    return req("DELETE", path)


def add_months(iso: str, n: int) -> str:
    y, m, d = [int(x) for x in iso.split("-")]
    m += n
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return f"{y:04d}-{m:02d}-{min(d, 28):02d}"


def in_clause(ids):
    return ",".join("?" * len(ids)), tuple(ids)


# ---------------------------------------------------------------------------
# Wipe
# ---------------------------------------------------------------------------

def wipe() -> dict:
    from backend.db.seed import ensure_additive_schema
    kind = backup_db()
    conn = db()
    ensure_additive_schema(conn)
    conn.commit()
    before = {
        "projects": q1(conn, "SELECT COUNT(*) n FROM projects")["n"],
        "units": q1(conn, "SELECT COUNT(*) n FROM units")["n"],
        "customers": q1(conn, "SELECT COUNT(*) n FROM customers")["n"],
        "bookings": q1(conn, "SELECT COUNT(*) n FROM bookings")["n"],
        "vendors": q1(conn, "SELECT COUNT(*) n FROM vendors")["n"],
        "agents": q1(conn, "SELECT COUNT(*) n FROM agents")["n"],
        "investors": q1(conn, "SELECT COUNT(*) n FROM investors")["n"],
    }
    haven = [r["id"] for r in q(conn, "SELECT id FROM projects WHERE name LIKE 'Haven%'")]
    non = [r["id"] for r in q(conn, "SELECT id FROM projects WHERE name NOT LIKE 'Haven%'")]

    def _ids(sql, params=()):
        return [r["id"] for r in q(conn, sql, params)]

    booking_ids = _ids(
        f"SELECT id FROM bookings WHERE project_id IN ({','.join('?' * len(non))})", tuple(non)
    ) if non else []

    if booking_ids:
        bp, bparams = in_clause(booking_ids)
        pay_ids = _ids(f"SELECT id FROM payments WHERE booking_id IN ({bp})", bparams)
        if pay_ids:
            pp, pparams = in_clause(pay_ids)
            conn.execute(f"DELETE FROM hold_token_applications WHERE payment_id IN ({pp})", pparams)
            conn.execute(f"DELETE FROM receipts WHERE payment_id IN ({pp})", pparams)
        conn.execute(f"DELETE FROM hold_token_applications WHERE booking_id IN ({bp})", bparams)
        conn.execute(f"DELETE FROM payments WHERE booking_id IN ({bp})", bparams)
        conn.execute(f"DELETE FROM installments WHERE booking_id IN ({bp})", bparams)
        conn.execute(f"DELETE FROM booking_cancellations WHERE booking_id IN ({bp})", bparams)
        conn.execute(f"DELETE FROM booking_transfers WHERE booking_id IN ({bp})", bparams)
        # Clear converted_booking_id before deleting bookings
        conn.execute(
            f"UPDATE unit_holds SET converted_booking_id=NULL WHERE converted_booking_id IN ({bp})",
            bparams,
        )
        comm_ids = _ids(f"SELECT id FROM agent_commissions WHERE booking_id IN ({bp})", bparams)
        if comm_ids:
            cp, cparams = in_clause(comm_ids)
            conn.execute(f"DELETE FROM agent_commission_payments WHERE commission_id IN ({cp})", cparams)
        conn.execute(f"DELETE FROM agent_commissions WHERE booking_id IN ({bp})", bparams)
        conn.execute(f"DELETE FROM bookings WHERE id IN ({bp})", bparams)

    if non:
        ph, pparams = in_clause(non)
        unit_ids = _ids(f"SELECT id FROM units WHERE project_id IN ({ph})", pparams)
        if unit_ids:
            uh, uhparams = in_clause(unit_ids)
            hold_ids = _ids(f"SELECT id FROM unit_holds WHERE unit_id IN ({uh})", uhparams)
            if hold_ids:
                hh, hparams = in_clause(hold_ids)
                conn.execute(f"DELETE FROM hold_token_applications WHERE hold_id IN ({hh})", hparams)
                conn.execute(f"DELETE FROM hold_receipts WHERE hold_id IN ({hh})", hparams)
                conn.execute(f"DELETE FROM hold_transactions WHERE hold_id IN ({hh})", hparams)
                conn.execute(f"DELETE FROM unit_holds WHERE id IN ({hh})", hparams)
        tmpl_ids = _ids(
            f"SELECT id FROM project_installment_templates WHERE project_id IN ({ph})", pparams
        )
        if tmpl_ids:
            th, tparams = in_clause(tmpl_ids)
            conn.execute(
                f"DELETE FROM project_installment_template_rules WHERE template_id IN ({th})", tparams
            )
            conn.execute(f"DELETE FROM project_installment_templates WHERE id IN ({th})", tparams)
        conn.execute(f"DELETE FROM site_logs WHERE project_id IN ({ph})", pparams)
        po_ids = _ids(f"SELECT id FROM purchase_orders WHERE project_id IN ({ph})", pparams)
        if po_ids:
            pop, poparams = in_clause(po_ids)
            conn.execute(f"DELETE FROM vendor_payments WHERE purchase_order_id IN ({pop})", poparams)
            conn.execute(f"DELETE FROM purchase_orders WHERE id IN ({pop})", poparams)
        conn.execute(f"DELETE FROM project_budget_lines WHERE project_id IN ({ph})", pparams)
        conn.execute(f"DELETE FROM units WHERE project_id IN ({ph})", pparams)
        conn.execute(f"UPDATE investor_agreements SET project_id=NULL WHERE project_id IN ({ph})", pparams)
        conn.execute(f"DELETE FROM projects WHERE id IN ({ph})", pparams)

    # Orphan hold cleanup (Haven units may keep holds)
    conn.execute(
        """DELETE FROM hold_token_applications WHERE hold_id IN (
             SELECT id FROM unit_holds WHERE unit_id NOT IN (SELECT id FROM units))"""
    )
    conn.execute(
        """DELETE FROM hold_receipts WHERE hold_id IN (
             SELECT id FROM unit_holds WHERE unit_id NOT IN (SELECT id FROM units))"""
    )
    conn.execute(
        """DELETE FROM hold_transactions WHERE hold_id IN (
             SELECT id FROM unit_holds WHERE unit_id NOT IN (SELECT id FROM units))"""
    )
    conn.execute("DELETE FROM unit_holds WHERE unit_id NOT IN (SELECT id FROM units)")

    conn.execute("DELETE FROM vendor_payments")
    conn.execute("DELETE FROM purchase_orders")
    conn.execute("DELETE FROM vendors")
    conn.execute("DELETE FROM investor_contributions")
    conn.execute("DELETE FROM investor_distributions")
    conn.execute("DELETE FROM investor_agreements")
    conn.execute("DELETE FROM investors")
    conn.execute("UPDATE bookings SET agent_id=NULL")
    conn.execute("DELETE FROM agent_commission_payments")
    conn.execute("DELETE FROM agent_commissions")
    conn.execute("DELETE FROM agents")
    conn.execute("DELETE FROM ledger_entries")
    conn.execute(
        """DELETE FROM customers WHERE id NOT IN (
             SELECT customer_id FROM bookings
             UNION SELECT customer_id FROM payments WHERE customer_id IS NOT NULL
             UNION SELECT hold_customer_id FROM units WHERE hold_customer_id IS NOT NULL
             UNION SELECT customer_id FROM unit_holds WHERE customer_id IS NOT NULL
             UNION SELECT from_customer_id FROM booking_transfers
             UNION SELECT to_customer_id FROM booking_transfers
             UNION SELECT customer_id FROM installments
           )"""
    )
    conn.commit()
    after = {
        "projects": q1(conn, "SELECT COUNT(*) n FROM projects")["n"],
        "haven_projects": len(q(conn, "SELECT id FROM projects WHERE name LIKE 'Haven%'")),
        "units": q1(conn, "SELECT COUNT(*) n FROM units")["n"],
        "customers": q1(conn, "SELECT COUNT(*) n FROM customers")["n"],
        "bookings": q1(conn, "SELECT COUNT(*) n FROM bookings")["n"],
        "vendors": q1(conn, "SELECT COUNT(*) n FROM vendors")["n"],
        "agents": q1(conn, "SELECT COUNT(*) n FROM agents")["n"],
        "investors": q1(conn, "SELECT COUNT(*) n FROM investors")["n"],
        "haven_payments": q1(conn, "SELECT COALESCE(SUM(amount),0) n FROM payments")["n"],
        "backup": kind,
        "haven_ids": haven,
    }
    conn.close()
    print(f"  wipe ok  projects {before['projects']} -> {after['projects']}  "
          f"vendors/agents/investors cleared  backup={kind}")
    return {"before": before, "after": after}


# ---------------------------------------------------------------------------
# World + timeline
# ---------------------------------------------------------------------------

def _plan(sale: int, dp: int, start: str, kind: str = "monthly12") -> list[dict]:
    rows = [{"amount": dp, "due_date": start, "type": "Booking"}]
    rem = sale - dp
    if kind == "monthly12":
        n, itype = 12, "Monthly"
    elif kind == "quarterly4":
        n, itype = 4, "Quarterly"
    else:
        n, itype = 12, "Monthly"
    base = rem // n
    extra = rem - base * n
    step = 1 if kind == "monthly12" else 3
    for i in range(n):
        amt = base + (extra if i == n - 1 else 0)
        due = add_months(start, step * (i + 1))
        typ = itype if i < n - 1 or kind != "quarterly4" else "Possession"
        if kind == "quarterly4" and i == n - 1:
            typ = "Possession"
        rows.append({"amount": amt, "due_date": due, "type": typ})
    return rows


def _pay(booking_id, customer_id, installment_id, amount, when, method="Cash", **extra):
    payload = {
        "booking_id": booking_id,
        "customer_id": customer_id,
        "installment_id": installment_id,
        "amount": int(amount),
        "payment_date": when,
        "method": method,
        "received_by": "Sim Admin",
        **extra,
    }
    return post("/api/payments", payload)


def _unit_detail(unit_id):
    return get(f"/api/units/{unit_id}")


def _unpaid_insts(unit_id):
    d = _unit_detail(unit_id)
    return d, [
        i for i in (d.get("installments") or [])
        if (i.get("remaining_amount") or 0) > 0
        and (i.get("status") or "") not in ("cancelled", "scheduled", "paid")
    ]


def _pay_due(unit_id, customer_id, booking_id, as_of, fraction=1.0, method="Cash"):
    paid = 0
    d, insts = _unpaid_insts(unit_id)
    for inst in insts:
        if inst["due_date"] > as_of:
            continue
        amt = int(inst["remaining_amount"] * fraction)
        if amt < 1:
            continue
        _pay(booking_id, customer_id, inst["id"], amt, as_of, method=method)
        paid += amt
    return paid


def _book(state, key, unit_key, cust_key, when, sale, dp, agent_key=None, plan="monthly12", poss=None):
    uid = state["units"][unit_key]["id"]
    cid = state["customers"][cust_key]["id"]
    aid = state["agents"][agent_key]["id"] if agent_key else None
    body = {
        "unit_id": uid,
        "project_id": state["project_id"],
        "customer_id": cid,
        "booking_date": when,
        "sale_price": sale,
        "base_sale_price": state["units"][unit_key]["price"],
        "booking_amount": dp,
        "agent_id": aid,
        "possession_date": poss,
        "installments": _plan(sale, dp, when, plan),
    }
    res = post("/api/bookings", body)
    bid = res["booking_id"]
    state["bookings"][key] = {
        "id": bid, "unit": unit_key, "unit_id": uid, "customer": cust_key,
        "customer_id": cid, "sale": sale, "dp": dp, "agent": agent_key, "date": when,
    }
    # pay booking installment
    detail = _unit_detail(uid)
    first = (detail.get("installments") or [None])[0]
    if first:
        rec = _pay(bid, cid, first["id"], min(dp, first["amount"]), when, method="Cheque",
                   bank="HBL", reference_number=f"CHQ-{key.upper()}")
        state["expected"]["cust_in"] += min(dp, first["amount"])
        state["bookings"][key]["receipt"] = rec.get("receipt")
    state["narrative"].append(f"{when}  {state['customers'][cust_key]['name']} booked {unit_key} "
                              f"for PKR {sale:,} (DP {dp:,})" + (f" via {agent_key}" if agent_key else " direct"))
    return bid


def build_world(state):
    print("  creating Gulberg Square...")
    proj = post("/api/projects", {
        "name": "Gulberg Square",
        "location": "MM Alam Road, Gulberg III",
        "description": "Mixed-use podium shops with residential tower. Lift, basement parking, backup generator.",
        "area": "Gulberg III",
        "city": "Lahore",
        "start_date": "2025-01-15",
        "expected_end_date": "2026-12-31",
        "status": "under_construction",
        "current_progress": 5,
        "number_of_floors": 5,
        "number_of_units": 34,
        "project_attributes": ["Lift", "Parking", "Generator", "Park", "Security"],
        "total_area_ghaz": 4200,
        "estimated_cost": 450000000,
    })
    pid = proj["id"]
    state["project_id"] = pid

    units_spec = []
    shop_prices = [22000000, 18500000, 25000000, 19800000, 30000000, 21000000, 24000000, 27500000]
    for i in range(8):
        n = i + 1
        attrs = ["Road Facing"] + (["Corner"] if n in (1, 8) else [])
        units_spec.append({
            "key": f"GS-G{n:02d}", "unit_no": f"GS-G{n:02d}", "unit_type": "Shop",
            "floor_number": 0, "area_ghaz": 45 + n * 4, "bedrooms": None, "bathrooms": 1,
            "residential_type": None, "base_sale_price": shop_prices[i],
            "booking_amount_required": shop_prices[i] // 10,
            "furnishing_status": "Builder condition",
            "unit_attributes": attrs, "block_tower": "Podium",
            "description": f"Ground shop {n} fronting MM Alam",
        })
    flat_prices = {
        (1, 2): 18000000, (1, 3): 28000000,
        (2, 2): 18500000, (2, 3): 28500000,
        (3, 2): 19000000, (3, 3): 29000000,
        (4, 2): 19500000, (4, 3): 30000000,
    }
    for floor in range(1, 5):
        for slot in range(1, 7):
            beds = 2 if slot <= 3 else 3
            baths = beds
            price = flat_prices[(floor, beds)] + slot * 50000
            tags = []
            if slot in (1, 6):
                tags.append("Corner")
            if slot in (2, 5):
                tags.append("Park Facing")
            if slot == 3:
                tags.append("Near Lift")
            if slot == 4:
                tags.append("West Open")
            rtype = "2 bed lounge" if beds == 2 else "3 bed DD"
            units_spec.append({
                "key": f"GS-{floor}{slot:02d}", "unit_no": f"GS-{floor}{slot:02d}",
                "unit_type": "Flat", "floor_number": floor, "area_ghaz": 90 if beds == 2 else 140,
                "bedrooms": beds, "bathrooms": baths, "residential_type": rtype,
                "base_sale_price": price, "booking_amount_required": price // 10,
                "furnishing_status": "Semi Furnished" if floor >= 3 else "Builder condition",
                "unit_attributes": tags, "block_tower": "Tower A",
                "description": f"{rtype} floor {floor}",
            })
    for n, price in ((1, 55000000), (2, 58000000)):
        units_spec.append({
            "key": f"GS-PH{n}", "unit_no": f"GS-PH{n}", "unit_type": "Flat",
            "floor_number": 5, "area_ghaz": 220, "bedrooms": 4, "bathrooms": 4,
            "residential_type": "Penthouse", "base_sale_price": price,
            "booking_amount_required": 8000000,
            "furnishing_status": "Fully furnished" if n == 1 else "Semi Furnished",
            "unit_attributes": ["Penthouse", "Roof Access", "Corner"],
            "block_tower": "Tower A", "description": f"Penthouse {n} with roof terrace",
        })

    for spec in units_spec:
        key = spec.pop("key")
        body = {"project_id": pid, **spec}
        created = post("/api/units", body)
        state["units"][key] = {"id": created["id"], "price": spec["base_sale_price"], "type": spec["unit_type"]}

    agents = [
        ("malik", "Malik Brokers", "Dealer", "0321-7001001", 2.0, "Gulberg dealer desk, walk-in traffic."),
        ("horizon", "Horizon Realty", "Broker", "0321-7001002", 2.5, "High-ticket broker network."),
        ("citylink", "City Link Associates", "Referral", "0321-7001003", 1.5, "Referral-only; later inactive."),
    ]
    for key, name, cat, phone, rate, desc in agents:
        a = post("/api/agents", {
            "name": name, "category": cat, "contact": phone,
            "default_rate_pct": rate, "description": desc, "status": "active",
        })
        state["agents"][key] = {"id": a["id"], "name": name, "rate": rate}

    vendors = [
        ("steel", "Punjab Steel Works", "Structural Steel", "042-111-2001", "TMT and structural sections"),
        ("elec", "Spark Electricals", "Electrical", "042-111-2002", "DB, cabling, fittings"),
        ("paint", "ColorCraft Paints", "Paint", "042-111-2003", "Exterior + interior"),
        ("plumb", "FlowLine Plumbing", "Plumbing", "042-111-2004", "PPR and sanitary"),
        ("tiles", "Royal Ceramics", "Tiles", "042-111-2005", "Floor and wall tiles"),
    ]
    for key, name, cat, phone, desc in vendors:
        v = post("/api/vendors", {
            "name": name, "category": cat, "contact": phone, "description": desc, "status": "active",
        })
        state["vendors"][key] = {"id": v["id"], "name": name}

    customers = [
        ("bilal", "Bilal Ahmed", "Tariq Ahmed", "37405-9900001-1", "0300-5110001"),
        ("hina", "Hina Qureshi", "Asif Qureshi", "37405-9900002-3", "0300-5110002"),
        ("usman", "Usman Tariq", "Tariq Mahmood", "37405-9900003-5", "0300-5110003"),
        ("saima", "Saima Riaz", "Riaz Ahmed", "37405-9900004-7", "0300-5110004"),
        ("omar", "Omar Farooq", "Farooq Aziz", "37405-9900005-9", "0300-5110005"),
        ("nadia", "Nadia Sheikh", "Imtiaz Sheikh", "37405-9900006-1", "0300-5110006"),
        ("kamal", "Kamal Hussain", "Ghulam Hussain", "37405-9900007-3", "0300-5110007"),
        ("farah", "Farah Malik", "Javed Malik", "37405-9900008-5", "0300-5110008"),
        ("zainab", "Zainab Ali", "Ali Haider", "37405-9900009-7", "0300-5110009"),
        ("imran", "Imran Cheema", "Sajjad Cheema", "37405-9900010-9", "0300-5110010"),
        ("rabia", "Rabia Noor", "Noor Muhammad", "37405-9900011-1", "0300-5110011"),
        ("shahid", "Shahid Mehmood", "Mehmood Khan", "37405-9900012-3", "0300-5110012"),
        ("asad", "Asad Javed", "Javed Iqbal", "37405-9900013-5", "0300-5110013"),
        ("tariq", "Tariq Nadeem", "Nadeem Akhtar", "37405-9900014-7", "0300-5110014"),
    ]
    for key, name, father, cnic, phone in customers:
        payload = {
            "name": name, "father_name": father, "cnic": cnic, "phone": phone,
            "emergency_contact_number": "0300-5990000",
            "email": f"{key}.sim@example.com",
            "address": f"House {hash(key) % 90 + 10}, Block C, DHA Phase 5, Lahore",
            "description": f"Sim customer ({key})",
        }
        if key == "bilal":
            payload.update({
                "nok_name": "Ayesha Ahmed", "nok_relationship": "Spouse",
                "nok_phone": "0300-5110099", "nok_cnic": "37405-9900099-1",
                "nok_address": "Same as residential",
            })
        c = post("/api/customers", payload)
        state["customers"][key] = {"id": c["id"], "name": name, "cnic": cnic}

    cats = {c["name"]: c["id"] for c in get("/api/budget/categories")}
    if "Plumbing" not in cats:
        created = post("/api/budget/categories", {"name": "Plumbing", "sort_order": 8})
        cats["Plumbing"] = created["id"]
    lines = [
        ("Structural Steel", 10_000_000, "Podium structure"),
        ("Electrical", 5_000_000, "Tower risers"),
        ("Plumbing", 2_000_000, "Wet areas"),
        ("Tiles & Finishing", 8_000_000, "Common + sample flat"),
    ]
    for name, planned, notes in lines:
        post("/api/budget/lines", {
            "project_id": pid, "category_id": cats[name],
            "planned_amount": planned, "notes": notes,
        })
        state["budget_cats"][name] = cats[name]

    invs = [
        ("khawaja", "Khawaja Capital", "Monthly Return", pid, 25_000_000, "2025-02-01", 1.5, None,
         "37405-8800001-1", "0321-8001001"),
        ("crescent", "Crescent Holdings", "Profit Sharing", pid, 40_000_000, "2025-02-01", None, 20.0,
         "37405-8800002-3", "0321-8001002"),
        ("metro", "Metro Seed Fund", "Profit Sharing", None, 15_000_000, "2025-02-01", None, 12.0,
         "37405-8800003-5", "0321-8001003"),
    ]
    for key, name, typ, project_id, agreed, idate, monthly, profit, cnic, phone in invs:
        inv = post("/api/investors", {
            "name": name, "cnic": cnic, "mobile_number": phone,
            "email": f"{key}@invest.pk", "description": f"{typ} partner",
            "status": "active", "investor_type": typ, "project_id": project_id,
            "agreed_amount": agreed, "investment_date": idate,
            "monthly_return_pct": monthly, "profit_share_pct": profit,
        })
        state["investors"][key] = {"id": inv["id"], "name": name, "agreed": agreed, "type": typ}

    # holds — GS-204 zero-token legacy-style; GS-G08 with token receipt
    put(f"/api/units/{state['units']['GS-204']['id']}/status", {
        "status": "hold", "hold_customer_id": state["customers"]["shahid"]["id"],
        "hold_until": "2027-06-30", "hold_notes": "Waiting for overseas remittance",
        "token_amount": 0,
    })
    hold_tok = post(f"/api/units/{state['units']['GS-G08']['id']}/holds", {
        "customer_id": state["customers"]["asad"]["id"],
        "hold_until": "2027-05-15",
        "notes": "Price negotiation · token received",
        "token_amount": 500_000,
        "receipt_date": "2025-01-15",
        "payment_method": "Cash",
        "received_by": "Admin",
    })
    state["holds"] = {
        "gs204": "zero-token",
        "gsg08": hold_tok,
    }
    state["expected"]["hold_in"] = 500_000
    state["expected"]["hold_out"] = 0

    # construction installment template for Gulberg
    put(f"/api/projects/{pid}/installment-template", {
        "name": "Gulberg construction milestones",
        "default_booking_bps": 1000,
        "rules": [
            {"label": "Foundation", "amount_bps": 2000, "trigger_kind": "construction",
             "milestone_progress": 10, "due_days_after_trigger": 7, "forecast_due_date": "2025-06-01"},
            {"label": "Structure 40%", "amount_bps": 2500, "trigger_kind": "construction",
             "milestone_progress": 40, "due_days_after_trigger": 7, "forecast_due_date": "2025-10-01"},
            {"label": "Structure 70%", "amount_bps": 2500, "trigger_kind": "construction",
             "milestone_progress": 70, "due_days_after_trigger": 7, "forecast_due_date": "2026-03-01"},
            {"label": "Finishing 90%", "amount_bps": 2000, "trigger_kind": "construction",
             "milestone_progress": 90, "due_days_after_trigger": 7, "forecast_due_date": "2026-07-01"},
            {"label": "Possession", "amount_bps": 1000, "trigger_kind": "construction",
             "milestone_progress": 100, "due_days_after_trigger": 0, "forecast_due_date": "2026-10-01"},
        ],
    })
    state["narrative"].append(
        "2025-01-15  Gulberg Square onboarded: 34 units, 2 holds (GS-204 zero-token, GS-G08 token 500k), milestone template"
    )


def run_timeline(state):
    pid = state["project_id"]
    exp = state["expected"]

    def site(when, prog, work, skilled=18, unskilled=40, mat="Cement, steel"):
        post("/api/site-logs", {
            "project_id": pid, "log_date": when, "engineer": "Engr. Waqas Rana",
            "workers_skilled": skilled, "workers_unskilled": unskilled,
            "material_used": mat, "work_done": work, "current_progress": prog,
        })
        state["last_progress"] = prog

    site("2025-01-20", 8, "Site clearance and layout of podium grid")

    # milestone template booking (scheduled until progress crosses thresholds)
    tmpl_preview = post(f"/api/projects/{pid}/installment-template/preview", {
        "sale_price": 18_500_000, "booking_amount": 1_850_000,
    })
    res = post("/api/bookings", {
        "unit_id": state["units"]["GS-105"]["id"],
        "project_id": pid,
        "customer_id": state["customers"]["shahid"]["id"],
        "booking_date": "2025-02-05",
        "sale_price": 18_500_000,
        "booking_amount": 1_850_000,
        "plan_source": "template",
        "template_id": tmpl_preview["template_id"],
        "installments": [],
    })
    state["bookings"]["shahid_m"] = {
        "id": res["booking_id"], "unit": "GS-105", "unit_id": state["units"]["GS-105"]["id"],
        "customer": "shahid", "customer_id": state["customers"]["shahid"]["id"],
        "sale": 18_500_000, "dp": 1_850_000, "date": "2025-02-05", "plan": "template",
    }
    # booking amount paid as normal (template milestones stay scheduled)
    post("/api/payments", {
        "booking_id": res["booking_id"],
        "customer_id": state["customers"]["shahid"]["id"],
        "amount": 1_850_000, "payment_date": "2025-02-05", "method": "Cheque",
        "notes": "Booking amount for milestone plan",
    })
    exp["cust_in"] += 1_850_000
    state["narrative"].append(
        "2025-02-05  Shahid Malik booked GS-105 on construction milestone template (all stages scheduled)"
    )

    # investors stage 1
    post(f"/api/investors/{state['investors']['khawaja']['id']}/contribute", {
        "amount": 15_000_000, "contribution_date": "2025-02-01", "notes": "First tranche",
    })
    post(f"/api/investors/{state['investors']['crescent']['id']}/contribute", {
        "amount": 20_000_000, "contribution_date": "2025-02-01", "notes": "First tranche",
    })
    post(f"/api/investors/{state['investors']['metro']['id']}/contribute", {
        "amount": 15_000_000, "contribution_date": "2025-02-01", "notes": "Company float",
    })
    exp["inv_in"] += 15_000_000 + 20_000_000 + 15_000_000
    state["narrative"].append("2025-02-01  Investor capital in: Khawaja 15M, Crescent 20M, Metro 15M")

    _book(state, "bilal", "GS-G01", "bilal", "2025-02-10", 22_000_000, 2_200_000, None, "monthly12", "2026-01-15")
    _book(state, "hina", "GS-101", "hina", "2025-02-12", 18_000_000, 2_000_000, "malik", "monthly12")
    _book(state, "usman", "GS-203", "usman", "2025-02-15", 28_500_000, 2_000_000, "horizon", "monthly12")
    _book(state, "saima", "GS-G03", "saima", "2025-02-20", 25_000_000, 1_500_000, "malik", "monthly12")
    # Saima only paid full DP via _book; leave rest unpaid
    _book(state, "nadia", "GS-102", "nadia", "2025-02-25", 18_000_000, 2_000_000, "horizon", "monthly12")
    _book(state, "omar", "GS-104", "omar", "2025-03-01", 18_200_000, 2_000_000, "citylink", "monthly12")
    _book(state, "farah", "GS-301", "farah", "2025-03-05", 29_000_000, 3_000_000, "malik", "monthly12")
    _book(state, "imran", "GS-PH1", "imran", "2025-03-10", 55_000_000, 8_000_000, "horizon", "quarterly4", "2026-06-01")
    _book(state, "rabia", "GS-G05", "rabia", "2025-03-12", 30_000_000, 12_000_000, None, "quarterly4", "2026-08-01")

    # Saima: she paid full booking inst; make one tiny extra later. Record she is chronic.

    steel = post("/api/purchase-orders", {
        "vendor_id": state["vendors"]["steel"]["id"], "project_id": pid,
        "material": "TMT bars 60 grade", "quantity": "40 Tons", "unit_cost": 300000,
        "total": 12_000_000, "category": "Structural Steel",
        "budget_category_id": state["budget_cats"]["Structural Steel"],
        "order_date": "2025-03-15", "expected_delivery_date": "2025-04-10",
        "site": "Podium", "notes": "Exceeds structural budget on purpose",
    })
    state["pos"]["steel"] = steel["id"]
    put(f"/api/purchase-orders/{steel['id']}/status", {"status": "approved"})
    site("2025-03-18", 15, "Podium columns starter bars", 22, 55, "TMT, cement")

    # April: monthly return + on-time payers
    dist = 225_000  # 1.5% of 15M
    post(f"/api/investors/{state['investors']['khawaja']['id']}/distribute", {
        "amount": dist, "distribution_date": "2025-04-01", "notes": "Apr monthly return",
    })
    exp["inv_out"] += dist
    exp["cust_in"] += _pay_due(state["units"]["GS-G01"]["id"], state["customers"]["bilal"]["id"],
                               state["bookings"]["bilal"]["id"], "2025-04-10", method="Bank Transfer")
    exp["cust_in"] += _pay_due(state["units"]["GS-101"]["id"], state["customers"]["hina"]["id"],
                               state["bookings"]["hina"]["id"], "2025-04-12", method="Bank Transfer")
    # Nadia one monthly
    exp["cust_in"] += _pay_due(state["units"]["GS-102"]["id"], state["customers"]["nadia"]["id"],
                               state["bookings"]["nadia"]["id"], "2025-04-25")

    put(f"/api/purchase-orders/{steel['id']}/status", {"status": "grn"})
    vp = post("/api/vendor-payments", {
        "vendor_id": state["vendors"]["steel"]["id"], "purchase_order_id": steel["id"],
        "amount": 5_000_000, "payment_date": "2025-04-12", "payment_method": "Bank Transfer",
        "reference_number": "FT-STEEL-1",
    })
    exp["vendor_out"] += 5_000_000
    elec = post("/api/purchase-orders", {
        "vendor_id": state["vendors"]["elec"]["id"], "project_id": pid,
        "material": "Main DB + risers", "quantity": "1 lot", "total": 4_300_000,
        "category": "Electrical", "budget_category_id": state["budget_cats"]["Electrical"],
        "order_date": "2025-04-14", "expected_delivery_date": "2025-05-20",
    })
    state["pos"]["elec"] = elec["id"]
    put(f"/api/purchase-orders/{elec['id']}/status", {"status": "approved"})

    # May: cancel Nadia, rebook Kamal, negative tests
    preview = get(f"/api/bookings/{state['bookings']['nadia']['id']}/cancel-preview")
    state["cancel_preview"] = preview
    cancel = post(f"/api/bookings/{state['bookings']['nadia']['id']}/cancel", {
        "reason": "Buyer emigrating; requested cancellation",
    })
    state["cancel_result"] = cancel
    state["narrative"].append(
        f"2025-05-01  Cancelled Nadia Sheikh GS-102  paid={cancel.get('total_paid')} "
        f"forfeit={cancel.get('forfeit_amount')} refund={cancel.get('refund_amount')} (not posted to cashbook)"
    )

    conn = db()
    inst_after_cancel = q(conn, "SELECT status, remaining_amount FROM installments WHERE booking_id=?",
                          (state["bookings"]["nadia"]["id"],))
    state["nadia_inst_after_cancel"] = inst_after_cancel
    conn.close()
    try:
        get("/api/dashboard")
        get("/api/customers")
    except ApiError as e:
        state["findings"].append({"sev": "high", "area": "dashboard", "msg": f"dashboard/customers error after cancel: {e}"})
    conn = db()
    inst_after_refresh = q(conn, "SELECT status, remaining_amount FROM installments WHERE booking_id=?",
                           (state["bookings"]["nadia"]["id"],))
    state["nadia_inst_after_refresh"] = inst_after_refresh
    conn.close()

    _book(state, "kamal", "GS-102", "kamal", "2025-05-05", 18_000_000, 2_000_000, "malik", "monthly12")

    try:
        post("/api/bookings", {
            "unit_id": state["units"]["GS-G01"]["id"], "project_id": pid,
            "customer_id": state["customers"]["tariq"]["id"], "booking_date": "2025-05-10",
            "sale_price": 22_000_000, "booking_amount": 1, "installments": [],
        })
        state["findings"].append({"sev": "high", "area": "booking", "msg": "double-book of GS-G01 was allowed"})
        state["neg"]["double_book"] = "ALLOWED"
    except ApiError as e:
        state["neg"]["double_book"] = f"blocked HTTP {e.status}"

    try:
        d, insts = _unpaid_insts(state["units"]["GS-G01"]["id"])
        inst = insts[0]
        _pay(state["bookings"]["bilal"]["id"], state["customers"]["bilal"]["id"],
             inst["id"], inst["remaining_amount"] + 50_000, "2025-05-10")
        state["neg"]["overpay"] = "ALLOWED"
        state["findings"].append({"sev": "high", "area": "payment", "msg": "over-remaining payment allowed"})
    except ApiError as e:
        state["neg"]["overpay"] = f"blocked HTTP {e.status}"

    post(f"/api/investors/{state['investors']['crescent']['id']}/contribute", {
        "amount": 20_000_000, "contribution_date": "2025-05-15", "notes": "Second tranche",
    })
    exp["inv_in"] += 20_000_000
    site("2025-05-16", 28, "Podium slab 2 and shop shutters", 25, 60, "Cement, steel")

    # June: Omar still missing; Bilal/Hina pay; agent partial
    exp["cust_in"] += _pay_due(state["units"]["GS-G01"]["id"], state["customers"]["bilal"]["id"],
                               state["bookings"]["bilal"]["id"], "2025-06-10", method="Bank Transfer")
    exp["cust_in"] += _pay_due(state["units"]["GS-101"]["id"], state["customers"]["hina"]["id"],
                               state["bookings"]["hina"]["id"], "2025-06-12", method="Bank Transfer")
    exp["cust_in"] += _pay_due(state["units"]["GS-G05"]["id"], state["customers"]["rabia"]["id"],
                               state["bookings"]["rabia"]["id"], "2025-06-12", method="Cheque")
    exp["cust_in"] += _pay_due(state["units"]["GS-PH1"]["id"], state["customers"]["imran"]["id"],
                               state["bookings"]["imran"]["id"], "2025-06-15", method="Bank Transfer")
    # Usman 50%
    exp["cust_in"] += _pay_due(state["units"]["GS-203"]["id"], state["customers"]["usman"]["id"],
                               state["bookings"]["usman"]["id"], "2025-06-20", fraction=0.5)

    malik = get(f"/api/agents/{state['agents']['malik']['id']}")
    unpaid = malik.get("commission_unpaid") or 0
    part = max(unpaid // 3, 1) if unpaid else 0
    if part:
        post(f"/api/agents/{state['agents']['malik']['id']}/pay", {
            "amount": part, "payment_date": "2025-06-25", "notes": "Partial June payout",
        })
        exp["agent_out"] += part
        state["malik_partial"] = part
    post(f"/api/investors/{state['investors']['khawaja']['id']}/distribute", {
        "amount": dist, "distribution_date": "2025-06-01", "notes": "Jun monthly return",
    })
    exp["inv_out"] += dist

    # July: Omar catch-up + transfer Farah -> Zainab
    exp["cust_in"] += _pay_due(state["units"]["GS-104"]["id"], state["customers"]["omar"]["id"],
                               state["bookings"]["omar"]["id"], "2025-07-08", method="Bank Transfer")
    state["narrative"].append("2025-07-08  Omar Farooq caught up missed installments in one transfer")
    try:
        post(f"/api/bookings/{state['bookings']['farah']['id']}/transfer", {
            "customer_id": state["customers"]["zainab"]["id"],
            "notes": "Family transfer to sister Zainab Ali",
            "transfer_date": "2025-07-20",
        })
        state["transfer_ok"] = True
        state["narrative"].append("2025-07-20  GS-301 transferred Farah Malik -> Zainab Ali")
    except ApiError as e:
        state["transfer_ok"] = False
        state["findings"].append({"sev": "high", "area": "transfer", "msg": str(e)})

    # continue Farah/Zainab payments under NEW customer id after transfer
    exp["cust_in"] += _pay_due(state["units"]["GS-301"]["id"], state["customers"]["zainab"]["id"],
                               state["bookings"]["farah"]["id"], "2025-07-25", method="Cheque")

    paint = post("/api/purchase-orders", {
        "vendor_id": state["vendors"]["paint"]["id"], "project_id": pid,
        "material": "Exterior emulsion sample", "total": 1_000_000, "category": "Paint",
        "budget_category_id": state["budget_cats"]["Tiles & Finishing"],
        "order_date": "2025-08-01",
    })
    state["pos"]["paint"] = paint["id"]
    put(f"/api/purchase-orders/{paint['id']}/status", {"status": "cancelled"})
    state["narrative"].append("2025-08-01  Cancelled draft paint PO 1M (budget should ignore it)")

    try:
        put(f"/api/purchase-orders/{steel['id']}/status", {"status": "cancelled"})
        state["neg"]["cancel_paid_po"] = "ALLOWED"
        state["findings"].append({"sev": "med", "area": "po", "msg": "cancelled a PO that already has payments"})
    except ApiError as e:
        state["neg"]["cancel_paid_po"] = f"blocked HTTP {e.status}"

    plumb = post("/api/purchase-orders", {
        "vendor_id": state["vendors"]["plumb"]["id"], "project_id": pid,
        "material": "PPR + sanitary stack", "total": 2_500_000, "category": "Plumbing",
        "budget_category_id": state["budget_cats"]["Plumbing"],
        "order_date": "2025-08-10",
    })
    state["pos"]["plumb"] = plumb["id"]
    put(f"/api/purchase-orders/{plumb['id']}/status", {"status": "approved"})
    put(f"/api/purchase-orders/{plumb['id']}/status", {"status": "grn"})
    post("/api/vendor-payments", {
        "vendor_id": state["vendors"]["plumb"]["id"], "purchase_order_id": plumb["id"],
        "amount": 2_500_000, "payment_date": "2025-08-20", "reference_number": "FT-PLUMB",
    })
    exp["vendor_out"] += 2_500_000

    tiles = post("/api/purchase-orders", {
        "vendor_id": state["vendors"]["tiles"]["id"], "project_id": pid,
        "material": "Floor tiles common area", "total": 3_000_000, "category": "Tiles",
        "budget_category_id": state["budget_cats"]["Tiles & Finishing"],
        "order_date": "2025-08-18",
    })
    state["pos"]["tiles"] = tiles["id"]
    put(f"/api/purchase-orders/{tiles['id']}/status", {"status": "approved"})
    put(f"/api/purchase-orders/{tiles['id']}/status", {"status": "grn"})
    post("/api/vendor-payments", {
        "vendor_id": state["vendors"]["tiles"]["id"], "purchase_order_id": tiles["id"],
        "amount": 1_200_000, "payment_date": "2025-08-28", "reference_number": "FT-TILE-1",
    })
    exp["vendor_out"] += 1_200_000

    site("2025-08-20", 40, "MEP first fix shops + sample flat", 20, 48, "Pipes, tiles")

    # Sep 2025 - Jun 2026 monthly loop for on-time + partial
    for month in range(9, 13):
        as_of = f"2025-{month:02d}-12"
        exp["cust_in"] += _pay_due(state["units"]["GS-G01"]["id"], state["customers"]["bilal"]["id"],
                                   state["bookings"]["bilal"]["id"], as_of, method="Bank Transfer")
        exp["cust_in"] += _pay_due(state["units"]["GS-101"]["id"], state["customers"]["hina"]["id"],
                                   state["bookings"]["hina"]["id"], as_of, method="Bank Transfer")
        exp["cust_in"] += _pay_due(state["units"]["GS-203"]["id"], state["customers"]["usman"]["id"],
                                   state["bookings"]["usman"]["id"], as_of, fraction=0.5)
        exp["cust_in"] += _pay_due(state["units"]["GS-301"]["id"], state["customers"]["zainab"]["id"],
                                   state["bookings"]["farah"]["id"], as_of)
        exp["cust_in"] += _pay_due(state["units"]["GS-102"]["id"], state["customers"]["kamal"]["id"],
                                   state["bookings"]["kamal"]["id"], as_of)
        if month % 2 == 1:
            post(f"/api/investors/{state['investors']['khawaja']['id']}/distribute", {
                "amount": dist, "distribution_date": f"2025-{month:02d}-01", "notes": "monthly return",
            })
            exp["inv_out"] += dist

    site("2025-11-10", 48, "Tower floor 3 slab", 28, 70, "Cement, steel")

    for month in range(1, 7):
        as_of = f"2026-{month:02d}-12"
        exp["cust_in"] += _pay_due(state["units"]["GS-G01"]["id"], state["customers"]["bilal"]["id"],
                                   state["bookings"]["bilal"]["id"], as_of, method="Bank Transfer")
        exp["cust_in"] += _pay_due(state["units"]["GS-101"]["id"], state["customers"]["hina"]["id"],
                                   state["bookings"]["hina"]["id"], as_of, method="Bank Transfer")
        exp["cust_in"] += _pay_due(state["units"]["GS-203"]["id"], state["customers"]["usman"]["id"],
                                   state["bookings"]["usman"]["id"], as_of, fraction=0.45)
        exp["cust_in"] += _pay_due(state["units"]["GS-301"]["id"], state["customers"]["zainab"]["id"],
                                   state["bookings"]["farah"]["id"], as_of)
        exp["cust_in"] += _pay_due(state["units"]["GS-102"]["id"], state["customers"]["kamal"]["id"],
                                   state["bookings"]["kamal"]["id"], as_of)
        exp["cust_in"] += _pay_due(state["units"]["GS-G05"]["id"], state["customers"]["rabia"]["id"],
                                   state["bookings"]["rabia"]["id"], as_of)
        exp["cust_in"] += _pay_due(state["units"]["GS-PH1"]["id"], state["customers"]["imran"]["id"],
                                   state["bookings"]["imran"]["id"], as_of, fraction=0.4)
        if month in (1, 3, 5):
            post(f"/api/investors/{state['investors']['khawaja']['id']}/distribute", {
                "amount": dist, "distribution_date": f"2026-{month:02d}-01", "notes": "monthly return",
            })
            exp["inv_out"] += dist

    # Saima tiny late token
    d, insts = _unpaid_insts(state["units"]["GS-G03"]["id"])
    if insts:
        token = min(200_000, insts[0]["remaining_amount"])
        _pay(state["bookings"]["saima"]["id"], state["customers"]["saima"]["id"],
             insts[0]["id"], token, "2025-12-20", method="Cash")
        exp["cust_in"] += token

    # Possession Bilal (should be fully/near paid) and Imran (still owing)
    try:
        post(f"/api/units/{state['units']['GS-G01']['id']}/possession", {"possession_date": "2026-01-20"})
        state["neg"]["poss_bilal"] = "ok"
        state["narrative"].append("2026-01-20  Possession delivered GS-G01 Bilal Ahmed")
    except ApiError as e:
        state["neg"]["poss_bilal"] = str(e)
    try:
        post(f"/api/units/{state['units']['GS-PH1']['id']}/possession", {"possession_date": "2026-03-15"})
        state["neg"]["poss_imran_owing"] = "ALLOWED (no outstanding check)"
        state["narrative"].append("2026-03-15  Possession delivered GS-PH1 while still owing")
    except ApiError as e:
        state["neg"]["poss_imran_owing"] = f"blocked HTTP {e.status}"

    post(f"/api/investors/{state['investors']['crescent']['id']}/distribute", {
        "amount": 2_000_000, "distribution_date": "2026-03-20", "notes": "Milestone profit share",
    })
    exp["inv_out"] += 2_000_000

    put(f"/api/agents/{state['agents']['citylink']['id']}", {
        "name": "City Link Associates", "category": "Referral", "contact": "0321-7001003",
        "default_rate_pct": 1.5, "description": "Referral-only; inactivated after Q1 2026.",
        "status": "inactive",
    })

    # unallocated vendor + unallocated customer payment
    post("/api/vendor-payments", {
        "vendor_id": state["vendors"]["elec"]["id"], "amount": 150_000,
        "payment_date": "2026-04-05", "notes": "Mobilisation, no PO",
    })
    exp["vendor_out"] += 150_000
    post("/api/payments", {
        "booking_id": state["bookings"]["usman"]["id"],
        "customer_id": state["customers"]["usman"]["id"],
        "amount": 300_000, "payment_date": "2026-04-08", "method": "Cash",
        "notes": "Unallocated - no installment_id",
    })
    exp["cust_in"] += 300_000
    exp["unalloc_cust"] = 300_000

    post("/api/ledger", {
        "entry_date": "2026-05-02", "narration": "Bank charges HBL ops account",
        "amount": 25000, "direction": "out", "category": "Bank charges",
    })
    exp["manual_out"] += 25_000
    post("/api/ledger", {
        "entry_date": "2026-05-03", "narration": "Misc scrap sale podium",
        "amount": 100_000, "direction": "in", "category": "Misc income",
    })
    exp["manual_in"] += 100_000
    site("2026-05-10", 70, "Finishes tower 1-3, shop shutters closing", 16, 35, "Paint, tiles")
    site("2026-08-01", 72, "Snagging and external paint sample", 12, 20, "Paint")

    try:
        delete(f"/api/investors/{state['investors']['khawaja']['id']}")
        state["neg"]["del_investor_money"] = "ALLOWED"
        state["findings"].append({"sev": "high", "area": "investor", "msg": "deleted investor with money history"})
    except ApiError as e:
        state["neg"]["del_investor_money"] = f"blocked HTTP {e.status}"

    # remaining steel + elec payments
    post("/api/vendor-payments", {
        "vendor_id": state["vendors"]["steel"]["id"], "purchase_order_id": state["pos"]["steel"],
        "amount": 7_000_000, "payment_date": "2026-06-15", "reference_number": "FT-STEEL-2",
    })
    exp["vendor_out"] += 7_000_000
    put(f"/api/purchase-orders/{state['pos']['elec']}/status", {"status": "grn"})
    post("/api/vendor-payments", {
        "vendor_id": state["vendors"]["elec"]["id"], "purchase_order_id": state["pos"]["elec"],
        "amount": 4_300_000, "payment_date": "2026-06-20", "reference_number": "FT-ELEC",
    })
    exp["vendor_out"] += 4_300_000

    malik = get(f"/api/agents/{state['agents']['malik']['id']}")
    rest = malik.get("commission_unpaid") or 0
    if rest > 0:
        post(f"/api/agents/{state['agents']['malik']['id']}/pay", {
            "amount": rest, "payment_date": "2026-07-10", "notes": "Clear Malik",
        })
        exp["agent_out"] += rest
    hor = get(f"/api/agents/{state['agents']['horizon']['id']}")
    hrest = hor.get("commission_unpaid") or 0
    if hrest > 0:
        half = max(hrest // 2, 1)
        post(f"/api/agents/{state['agents']['horizon']['id']}/pay", {
            "amount": half, "payment_date": "2026-07-12", "notes": "Partial Horizon",
        })
        exp["agent_out"] += half

    # temp project for site_log delete guard
    tmp = post("/api/projects", {
        "name": "Tmp Sim SiteOnly", "city": "Lahore", "status": "planning",
    })
    post("/api/site-logs", {
        "project_id": tmp["id"], "log_date": "2026-08-01", "engineer": "Engr. Test",
        "work_done": "Guard test only",
    })
    try:
        delete(f"/api/projects/{tmp['id']}")
        state["neg"]["del_proj_sitelog"] = "ALLOWED (orphan risk or cascaded)"
    except ApiError as e:
        state["neg"]["del_proj_sitelog"] = f"blocked HTTP {e.status}: {e.body[:200]}"
    # cleanup temp
    conn = db()
    conn.execute("DELETE FROM site_logs WHERE project_id=?", (tmp["id"],))
    conn.execute("DELETE FROM project_budget_lines WHERE project_id=?", (tmp["id"],))
    try:
        conn.execute("DELETE FROM projects WHERE id=?", (tmp["id"],))
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
    conn.close()

    state["narrative"].append("2026-08  Simulation clock stops near today. Saima still chronic overdue.")


def new_state(wipe_info):
    return {
        "wipe": wipe_info,
        "project_id": None,
        "units": {},
        "customers": {},
        "agents": {},
        "vendors": {},
        "investors": {},
        "bookings": {},
        "pos": {},
        "budget_cats": {},
        "expected": {
            "cust_in": 0, "vendor_out": 0, "agent_out": 0,
            "inv_in": 0, "inv_out": 0, "manual_in": 0, "manual_out": 0,
            "hold_in": 0, "hold_out": 0,
            "haven_payments": (wipe_info or {}).get("after", {}).get("haven_payments", 0),
            "unalloc_cust": 0,
        },
        "narrative": [],
        "findings": [],
        "checks": [],
        "neg": {},
        "last_progress": 0,
        "ux_notes": [],
    }


def save_state(state):
    Path(os.path.dirname(STATE_PATH)).mkdir(parents=True, exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, default=str)


def load_state():
    with open(STATE_PATH, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Assert + report
# ---------------------------------------------------------------------------

def _check(state, name, expected, actual, sev="high", note=""):
    ok = expected == actual
    state["checks"].append({
        "name": name, "expected": expected, "actual": actual, "pass": ok,
        "sev": sev, "note": note,
    })
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: expected={expected} actual={actual} {note}")
    return ok


def _check_close(state, name, expected, actual, sev="high", note=""):
    return _check(state, name, int(expected or 0), int(actual or 0), sev, note)


def run_assert(state):
    pid = state["project_id"]
    exp = state["expected"]
    print("\n=== Assertions ===")

    # trigger global refresh (this is where cancel resurrection shows)
    dash_all = get("/api/dashboard")
    dash_g = get(f"/api/dashboard?project_ids={pid}")
    proj = get(f"/api/projects/{pid}")
    units = get(f"/api/units?project_id={pid}")
    customers = {c["id"]: c for c in get("/api/customers")}
    agents = {a["id"]: a for a in get("/api/agents")}
    vendors = {v["id"]: v for v in get("/api/vendors")}
    investors = {i["id"]: i for i in get("/api/investors")}
    ledger = get("/api/ledger")
    recovery = get(f"/api/recovery?project_ids={pid}")
    ageing = get("/api/reports/ageing")
    sales = get("/api/reports/sales")
    budget = get(f"/api/budget/summary?project_id={pid}")
    audit = get("/api/audit?limit=200")
    portal_dir = get("/api/portal")

    live_total = len(units)
    live_hold = sum(1 for u in units if u.get("raw_status") == "hold" or u.get("status") == "hold")
    live_avail = sum(1 for u in units if (u.get("raw_status") or u.get("status")) == "available")
    live_booked = sum(1 for u in units if (u.get("raw_status") or u.get("status")) in ("booked", "sold"))
    live_deliv = sum(1 for u in units if (u.get("raw_status") or u.get("status")) in ("possession_delivered", "delivered"))

    _check_close(state, "gulberg live unit count", 34, live_total)
    _check_close(state, "project.number_of_units stored", 34, proj.get("number_of_units"), "med",
                 "planning field; live count also returned as total_units")
    _check_close(state, "dashboard gulberg total_units", live_total, dash_g["kpi"]["total_units"])
    _check_close(state, "dashboard gulberg hold", live_hold, dash_g["kpi"]["hold"])
    _check_close(state, "site progress last write", state.get("last_progress") or 72, proj.get("current_progress") or proj.get("progress"))

    # cancel installments
    conn = db()
    nadia_now = q(conn, "SELECT status, COUNT(*) n FROM installments WHERE booking_id=? GROUP BY status",
                  (state["bookings"]["nadia"]["id"],))
    cancelled_n = sum(r["n"] for r in nadia_now if r["status"] == "cancelled")
    resurrected = sum(r["n"] for r in nadia_now if r["status"] != "cancelled" and r["status"] != "paid")
    _check(state, "cancelled installments stay cancelled after dashboard refresh", True, resurrected == 0,
           note=f"statuses={nadia_now}")
    if resurrected:
        state["findings"].append({
            "sev": "high", "area": "installments.refresh_statuses",
            "msg": "Cancelled installment rows were rewritten after dashboard/customer list (refresh_statuses ignores cancelled).",
        })

    # transfer paid totals
    farah = customers.get(state["customers"]["farah"]["id"], {})
    zainab = customers.get(state["customers"]["zainab"]["id"], {})
    conn = db()
    pays_farah = q1(conn, "SELECT COALESCE(SUM(amount),0) n FROM payments WHERE booking_id=? AND customer_id=?",
                    (state["bookings"]["farah"]["id"], state["customers"]["farah"]["id"],))["n"]
    pays_zainab = q1(conn, "SELECT COALESCE(SUM(amount),0) n FROM payments WHERE booking_id=? AND customer_id=?",
                     (state["bookings"]["farah"]["id"], state["customers"]["zainab"]["id"],))["n"]
    bk = q1(conn, "SELECT customer_id, final_sale_price FROM bookings WHERE id=?",
            (state["bookings"]["farah"]["id"],))
    xfer = q1(conn, "SELECT transfer_date FROM booking_transfers WHERE booking_id=? ORDER BY id DESC LIMIT 1",
              (state["bookings"]["farah"]["id"],))
    conn.close()
    _check(state, "transfer booking owner is Zainab", state["customers"]["zainab"]["id"], bk["customer_id"] if bk else None)
    if xfer and xfer["transfer_date"] == TODAY:
        state["findings"].append({
            "sev": "med", "area": "transfer",
            "msg": f"transfer_date stored as today ({TODAY}) not the requested 2025-07-20 (body field ignored).",
        })
    _check_close(state, "transfer: Farah has no payment rows on moved booking", 0, pays_farah)
    _check(state, "transfer: Zainab owns payment rows", True, pays_zainab > 0, note=f"zainab_paid={pays_zainab}")

    z_out = zainab.get("outstanding")
    z_val = zainab.get("total_value") or zainab.get("total_to_pay")
    if z_val and pays_zainab == 0 and (zainab.get("total_paid") or 0) == 0:
        state["findings"].append({
            "sev": "high", "area": "customers.enrich",
            "msg": f"Zainab shows value={z_val} paid={zainab.get('total_paid')} outstanding={z_out} after inheriting GS-301.",
        })

    # cashbook
    inflow = ledger.get("inflow") or ledger.get("revenue") or 0
    outflow = ledger.get("outflow") or ledger.get("expenses") or 0
    exp_in = (exp["haven_payments"] + exp["cust_in"] + exp["inv_in"] + exp["manual_in"]
              + exp.get("hold_in", 0))
    exp_out = (exp["vendor_out"] + exp["agent_out"] + exp["inv_out"] + exp["manual_out"]
               + exp.get("hold_out", 0))
    _check_close(state, "cashbook inflow (company-wide)", exp_in, inflow,
                 note="includes leftover Haven customer receipts + hold tokens")
    _check_close(state, "cashbook outflow", exp_out, outflow)
    state["ux_notes"].append({
        "sev": "med", "screen": "Accounts",
        "msg": "Cashbook is company-wide (now labelled in UI). Dashboard project filter will not match Accounts net cash.",
    })

    # hold token accounting — inflow once, no double-count if later applied
    hold_entries = [e for e in (ledger.get("entries") or []) if e.get("source") == "hold"]
    hold_in_sum = sum(int(e.get("inflow") or 0) for e in hold_entries)
    hold_out_sum = sum(int(e.get("outflow") or 0) for e in hold_entries)
    _check_close(state, "hold token cashbook inflow", exp.get("hold_in", 0), hold_in_sum)
    _check_close(state, "hold token cashbook outflow", exp.get("hold_out", 0), hold_out_sum)

    # milestone template booking
    sh = _unit_detail(state["units"]["GS-105"]["id"])
    sched = [i for i in (sh.get("installments") or []) if i.get("status") == "scheduled"]
    active_m = [i for i in (sh.get("installments") or []) if i.get("status") in ("pending", "partial", "overdue", "paid")]
    _check(state, "GS-105 has activated milestones after progress >=70%", True, len(active_m) >= 3,
           sev="high")
    _check(state, "GS-105 still has later scheduled milestones", True, len(sched) >= 1, sev="med")
    recv = get(f"/api/recovery?project_id={state['project_id']}")
    recv_ids = {r.get("id") for r in (recv.get("overdue") or [])}
    sched_ids = {i["id"] for i in sched}
    _check(state, "scheduled milestones excluded from recovery overdue", True,
           not (sched_ids & recv_ids), sev="high")

    bilal = get(f"/api/customers/{state['customers']['bilal']['id']}")
    _check(state, "Bilal NOK name persisted", "Ayesha Ahmed", bilal.get("nok_name"))
    _check(state, "Bilal father separate from NOK", "Tariq Ahmed", bilal.get("father_name"))
    _check(state, "Bilal NOK searchable fields present", True,
           bool(bilal.get("nok_phone") and bilal.get("nok_cnic")))

    g08 = _unit_detail(state["units"]["GS-G08"]["id"])
    _check(state, "GS-G08 still on hold with token history", "hold",
           (g08.get("unit") or {}).get("status") or (g08.get("unit") or {}).get("raw_status"))
    hold_amt = ((g08.get("hold") or {}).get("hold") or {}).get("token_amount")
    _check(state, "GS-G08 hold token amount 500k", 500_000, hold_amt)

    # vendors vs dashboard payable
    v_pay = sum(v.get("total_payable") or 0 for v in vendors.values())
    v_paid = sum(v.get("total_paid") or 0 for v in vendors.values())
    v_bal = sum(v.get("balance") or 0 for v in vendors.values())
    a_unpaid = sum(a.get("commission_unpaid") or 0 for a in agents.values())
    dash_pay = dash_all["kpi"]["payable"]
    honest_payable = v_bal + a_unpaid
    _check_close(state, "dashboard payable == vendor balances + agent unpaid", honest_payable, dash_pay,
                 note=f"vendor_bal={v_bal} agent_unpaid={a_unpaid}")
    if dash_pay != honest_payable:
        state["findings"].append({
            "sev": "high", "area": "dashboard.payable",
            "msg": f"Dashboard payable {dash_pay} != vendor.balance+agent.unpaid {honest_payable}. Likely PO/payment join fan-out and/or reversed commissions and/or cancelled POs.",
        })

    # reversed commission still in agent unpaid KPI
    conn = db()
    rev = q1(conn, "SELECT COUNT(*) n FROM agent_commissions WHERE status='reversed'")
    kpi_unpaid = q1(conn, """SELECT COALESCE(SUM(commission_amount - paid_amount),0) n FROM agent_commissions
                             WHERE status != 'reversed' AND paid_amount < commission_amount""")
    conn.close()
    api_unpaid = sum((a.get("commission_unpaid") or 0) for a in agents.values())
    _check_close(state, "agent unpaid excludes reversed commissions", kpi_unpaid["n"] if kpi_unpaid else 0, api_unpaid,
                 note=f"reversed_rows={rev['n'] if rev else 0}")

    # budget cancelled PO
    fin = next((b for b in budget if b.get("category_name") == "Tiles & Finishing"), None)
    steel_b = next((b for b in budget if b.get("category_name") == "Structural Steel"), None)
    elec_b = next((b for b in budget if b.get("category_name") == "Electrical"), None)
    plumb_b = next((b for b in budget if b.get("category_name") == "Plumbing"), None)
    if fin:
        _check_close(state, "budget finishing actual excludes cancelled 1M paint PO", 3_000_000, fin.get("actual_spent") or fin.get("spent") or 0)
        if (fin.get("actual_spent") or fin.get("spent") or 0) == 4_000_000:
            state["findings"].append({
                "sev": "med", "area": "budget.summary",
                "msg": "Cancelled paint PO 1M is included in Tiles & Finishing actual_spent.",
            })
    if steel_b:
        _check(state, "structural budget Exceeded", "Exceeded", steel_b.get("status") or steel_b.get("budget_status"))
    if elec_b:
        st = elec_b.get("status") or elec_b.get("budget_status")
        _check(state, "electrical budget Near Limit", True, st in ("Near Limit", "NearLimit"), note=str(st))
    if plumb_b:
        _check(state, "plumbing budget Exceeded", "Exceeded", plumb_b.get("status") or plumb_b.get("budget_status"))

    # investors
    kh = investors[state["investors"]["khawaja"]["id"]]
    cr = investors[state["investors"]["crescent"]["id"]]
    _check_close(state, "khawaja contributed", 15_000_000, kh.get("investment_amount"))
    _check_close(state, "crescent contributed", 40_000_000, cr.get("investment_amount"))
    _check_close(state, "khawaja agreed", 25_000_000, kh.get("agreed_amount"))
    if kh.get("outstanding_return") != max((kh.get("investment_amount") or 0) - (kh.get("total_return_received") or 0), 0):
        state["findings"].append({"sev": "low", "area": "investor", "msg": "outstanding_return formula mismatch"})

    # unallocated payment drift
    usman_u = _unit_detail(state["units"]["GS-203"]["id"])
    inst_rem = sum(i.get("remaining_amount") or 0 for i in usman_u.get("installments") or [])
    sum_out = usman_u.get("summary", {}).get("outstanding")
    if abs((inst_rem or 0) - (sum_out or 0)) >= 300_000:
        state["findings"].append({
            "sev": "med", "area": "payments",
            "msg": f"Usman unallocated 300k: installment remaining={inst_rem} vs unit summary outstanding={sum_out}. Recovery vs unit detail disagree.",
        })
        _check(state, "unallocated payment updates installment remaining", True, False,
               sev="med", note=f"inst_rem={inst_rem} summary_out={sum_out}")
    else:
        _check(state, "unallocated payment reflected consistently", True, True)

    # possession booking still active
    bilal_u = _unit_detail(state["units"]["GS-G01"]["id"])
    raw = (bilal_u.get("unit") or {}).get("raw_status") or (bilal_u.get("unit") or {}).get("status")
    bkstat = (bilal_u.get("booking") or {}).get("status")
    _check(state, "possessed unit display delivered/possession", True,
           raw in ("possession_delivered", "delivered") or (bilal_u.get("unit") or {}).get("status") == "delivered")
    if bkstat == "active":
        state["findings"].append({
            "sev": "low", "area": "possession",
            "msg": "Booking stays status=active after possession_delivered. Realistic ops usually mark completed.",
        })
    if state["neg"].get("poss_imran_owing", "").startswith("ALLOWED"):
        state["findings"].append({
            "sev": "med", "area": "possession",
            "msg": "Possession allowed on GS-PH1 while installments still outstanding.",
        })

    # negative tests
    _check(state, "double-book blocked", True, str(state["neg"].get("double_book", "")).startswith("blocked"))
    _check(state, "overpay blocked", True, str(state["neg"].get("overpay", "")).startswith("blocked"))
    _check(state, "delete investor with money blocked", True, str(state["neg"].get("del_investor_money", "")).startswith("blocked"))

    delp = state["neg"].get("del_proj_sitelog", "")
    if delp.startswith("ALLOWED"):
        state["findings"].append({
            "sev": "med", "area": "projects.delete",
            "msg": "Project with only site_logs could be deleted (no guard). FK may 500 or orphan logs.",
        })
    elif "500" in delp:
        state["findings"].append({
            "sev": "med", "area": "projects.delete",
            "msg": f"delete_project with site_logs raised server error instead of 400: {delp}",
        })

    # portal
    names = " ".join((c.get("name") or "") for c in (portal_dir if isinstance(portal_dir, list) else portal_dir.get("customers", [])))
    _check(state, "portal lists Bilal (active booking)", True, "Bilal" in names, sev="med")
    try:
        pbilal = get(f"/api/portal?customer_id={state['customers']['bilal']['id']}")
        _check(state, "portal detail for Bilal", True, bool(pbilal), sev="med")
    except ApiError as e:
        _check(state, "portal detail for Bilal", True, False, note=str(e))

    # saima overdue
    rec_over = recovery.get("overdue") or recovery.get("items") or []
    if isinstance(recovery, dict) and not rec_over:
        rec_over = dash_g.get("overdue") or []
    saima_hit = any("Saima" in str(r.get("customer_name") or r.get("customer") or "") for r in rec_over)
    _check(state, "Saima appears on Gulberg overdue/recovery", True, saima_hit, sev="med")

    # sales report has Gulberg
    g_sales = [r for r in (sales or []) if "Gulberg" in str(r.get("project_name") or "")]
    _check(state, "sales report includes Gulberg Square", True, len(g_sales) == 1, sev="med")

    # audit presence
    actions = " ".join(str(a.get("action")) for a in (audit if isinstance(audit, list) else audit.get("items", [])))
    _check(state, "audit has booking/payment activity", True,
           ("created" in actions or "recorded" in actions or "cancelled" in actions), sev="low")
    state["ux_notes"].append({
        "sev": "low", "screen": "Demand notices",
        "msg": "Preview is honest now; WhatsApp/email/PDF still not connected. late_fee_pct setting unused.",
    })
    state["ux_notes"].append({
        "sev": "low", "screen": "Activity",
        "msg": "Audit still omits most CRUD and site logs (payments/bookings/money are logged).",
    })

    # cancel refund not in cashbook
    if state.get("cancel_result", {}).get("refund_amount", 0) > 0:
        state["findings"].append({
            "sev": "med", "area": "cancel",
            "msg": f"Cancel computed refund {state['cancel_result']['refund_amount']} but no cashbook/ledger outflow was posted.",
        })

    conn = db()
    state["snapshot"] = {
        "gulberg_units": live_total,
        "gulberg_hold": live_hold,
        "gulberg_available": live_avail,
        "gulberg_booked": live_booked,
        "gulberg_delivered": live_deliv,
        "dash_all_payable": dash_pay,
        "dash_g_receivable": dash_g["kpi"]["receivable"],
        "cash_in": inflow,
        "cash_out": outflow,
        "cash_net": (ledger.get("net") or ledger.get("profit")),
        "vendor_payable": v_pay,
        "vendor_paid": v_paid,
        "vendor_balance": v_bal,
        "agent_unpaid": a_unpaid,
        "ageing": {
            "d30": (ageing or {}).get("d30"),
            "d60": (ageing or {}).get("d60"),
            "d90": (ageing or {}).get("d90"),
            "items": len((ageing or {}).get("items") or []),
        },
        "budget": budget,
        "farah_paid_rows": pays_farah,
        "zainab_paid_rows": pays_zainab,
        "zainab_api_paid": zainab.get("total_paid"),
        "zainab_api_out": z_out,
        "nadia_inst": nadia_now,
        "progress": proj.get("current_progress") or proj.get("progress"),
    }
    conn.close()
    return state


def write_report(state):
    w = state.get("wipe") or {}
    after = (w.get("after") or {})
    checks = state.get("checks") or []
    passed = sum(1 for c in checks if c["pass"])
    failed = [c for c in checks if not c["pass"]]
    findings = state.get("findings") or []
    ux = state.get("ux_notes") or []
    snap = state.get("snapshot") or {}
    exp = state.get("expected") or {}

    def money(n):
        try:
            return f"PKR {int(n):,}"
        except (TypeError, ValueError):
            return str(n)

    lines = [
        "# Gulberg Square simulation report",
        "",
        f"Ran against `{BASE}` on {TODAY}. Backup: `db/haven.pre-sim.db` ({after.get('backup')}).",
        "",
        "## 1. Wipe / keep / create",
        "",
        f"- Kept Haven projects: **{after.get('haven_projects')}** (ids {after.get('haven_ids')}). Haven units/bookings/customer receipts untouched.",
        f"- After wipe: projects={after.get('projects')}, units={after.get('units')}, customers={after.get('customers')}, bookings={after.get('bookings')}, vendors/agents/investors=0.",
        f"- Haven customer receipts still in cashbook: {money(exp.get('haven_payments'))}.",
        f"- Created **Gulberg Square** (id {state.get('project_id')}): 8 shops + 24 flats + 2 penthouses = 34 units; 2 holds; 14 customers; 3 agents; 5 vendors; 3 investors; 4 budget lines.",
        "",
        "## 2. Narrative",
        "",
    ]
    for n in state.get("narrative") or []:
        lines.append(f"- {n}")
    lines += [
        "- Saima Riaz (GS-G03): tiny token payment only — chronic overdue for Recovery/Demand.",
        "- Usman Tariq: half-pays + one unallocated 300k cash (no installment id) — schedule vs cash disagree.",
        "- City Link Associates set inactive after Omar's booking commission existed.",
        "",
        "## 3. Expected vs actual",
        "",
        f"**{passed}/{len(checks)} checks passed.**",
        "",
        "| Check | Result | Expected | Actual | Notes |",
        "|---|---|---|---|---|",
    ]
    for c in checks:
        mark = "PASS" if c["pass"] else "FAIL"
        lines.append(f"| {c['name']} | {mark} | {c['expected']} | {c['actual']} | {c.get('note') or ''} |")
    lines += [
        "",
        "### Snapshot",
        "",
        f"- Gulberg inventory: {snap.get('gulberg_units')} total / {snap.get('gulberg_available')} available / {snap.get('gulberg_hold')} hold / {snap.get('gulberg_booked')} booked / {snap.get('gulberg_delivered')} delivered. Progress {snap.get('progress')}%.",
        f"- Cashbook in {money(snap.get('cash_in'))} / out {money(snap.get('cash_out'))} / net {money(snap.get('cash_net'))}.",
        f"- Vendor payable {money(snap.get('vendor_payable'))} paid {money(snap.get('vendor_paid'))} balance {money(snap.get('vendor_balance'))}. Agent unpaid {money(snap.get('agent_unpaid'))}. Dashboard payable {money(snap.get('dash_all_payable'))}.",
        f"- Gulberg receivable (dashboard filter) {money(snap.get('dash_g_receivable'))}.",
        f"- Ageing report: `{snap.get('ageing')}`.",
        f"- Transfer paid rows: Farah {money(snap.get('farah_paid_rows'))} vs Zainab {money(snap.get('zainab_paid_rows'))} (API paid {money(snap.get('zainab_api_paid'))}, outstanding {money(snap.get('zainab_api_out'))}).",
        f"- Nadia installment statuses after refresh: `{snap.get('nadia_inst')}`.",
        f"- Negative tests: `{json.dumps(state.get('neg') or {}, default=str)}`.",
        f"- Cancel preview/result: `{state.get('cancel_preview')}` / `{state.get('cancel_result')}`.",
        "",
        "## 4. Data mapping / calculation / fit",
        "",
    ]
    if not findings:
        lines.append("No calculation defects flagged in this run.")
    for fnd in findings:
        lines.append(f"- **{fnd.get('sev', '?').upper()}** `{fnd.get('area')}` — {fnd.get('msg')}")
    lines += [
        "",
        "Haven seed quirks left untouched: Commercial Hub all `sold` without bookings; some Residencia units `booked` without rows.",
        "",
        "## 5. UX / functionality",
        "",
    ]
    for u in ux:
        lines.append(f"- **{u.get('sev', '?').upper()}** _{u.get('screen')}_ — {u.get('msg')}")
    lines += [
        "",
        "## 6. Fixes applied this pass",
        "",
        "- Cancelled installments no longer resurrected by `refresh_statuses`.",
        "- Transfer moves `payments.customer_id` and accepts `transfer_date`.",
        "- Dashboard payable matches vendor balances + non-reversed agent unpaid.",
        "- Budget actual excludes cancelled POs; booking/receipt numbers use max suffix.",
        "- Unallocated customer payments apply FIFO to installments.",
        "- `delete_project` returns 400 when site logs exist.",
        "- UX: Hold/Release, pay date/method, possession date + outstanding warn, cancel reason, booking confirm, project budget table, ageing line items, honest demand preview, Accounts labelled company-wide.",
        "",
        "## 7. Still open / product choices",
        "",
        "- Cancel refund is computed but not posted to cashbook.",
        "- Possession allowed while outstanding; booking stays `active` (so portal still lists them).",
        "- Cashbook has no project filter.",
        "- Demand WhatsApp/PDF/email not built. Multi-agreement investors not in UI.",
        "- Haven seed: Commercial Hub sold without bookings; leftover verify customers on Heights.",
        "",
        "Replay: `python -m backend.simulate wipe && python -m backend.simulate run`  ",
        "Re-check after fixes: `python -m backend.simulate assert`",
        "",
    ]
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n  report -> {REPORT_PATH}  ({passed}/{len(checks)} passed, {len(failed)} failed, {len(findings)} findings)")


def cmd_wipe():
    print("\n=== Wipe ===")
    get("/api/health")
    info = wipe()
    save_state(new_state(info))
    return info


def cmd_run():
    print("\n=== Simulate run ===")
    get("/api/health")
    try:
        state = load_state()
    except FileNotFoundError:
        state = new_state(None)
    if not state.get("wipe"):
        print("  no wipe snapshot in state; run wipe first (continuing with live DB)")
        conn = db()
        state["wipe"] = {"after": {
            "haven_payments": q1(conn, "SELECT COALESCE(SUM(amount),0) n FROM payments")["n"],
            "haven_ids": [r["id"] for r in q(conn, "SELECT id FROM projects WHERE name LIKE 'Haven%'")],
        }}
        conn.close()
        state["expected"]["haven_payments"] = state["wipe"]["after"]["haven_payments"]
    build_world(state)
    run_timeline(state)
    save_state(state)
    run_assert(state)
    save_state(state)
    write_report(state)
    return state


def cmd_assert():
    print("\n=== Assert only ===")
    get("/api/health")
    state = load_state()
    state["checks"] = []
    state["findings"] = []
    state["ux_notes"] = []
    run_assert(state)
    save_state(state)
    write_report(state)
    return state


def main(argv=None):
    argv = list(argv or sys.argv[1:])
    cmd = (argv[0] if argv else "help").lower()
    if cmd == "wipe":
        cmd_wipe()
    elif cmd == "run":
        cmd_run()
    elif cmd == "assert":
        cmd_assert()
    elif cmd == "all":
        cmd_wipe()
        cmd_run()
    else:
        print("usage: python -m backend.simulate [wipe|run|assert|all]")
        sys.exit(2)


if __name__ == "__main__":
    main()
