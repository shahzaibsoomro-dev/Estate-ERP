"""Input validation found while importing a real workbook."""
from datetime import date, timedelta

import pytest
from conftest import login


@pytest.fixture
def booking(as_role, world):
    from backend.database import get_db
    with get_db(world["a_db"]) as conn:
        row = conn.execute("""SELECT b.id, b.customer_id, b.final_sale_price,
                                     COALESCE((SELECT SUM(amount) FROM payments p WHERE p.booking_id=b.id),0)
                              FROM bookings b WHERE b.status='active'
                                AND b.final_sale_price > COALESCE((SELECT SUM(amount) FROM payments p WHERE p.booking_id=b.id),0) + 10
                              LIMIT 1""").fetchone()
        cancelled = conn.execute("SELECT id, customer_id FROM bookings WHERE status='cancelled' LIMIT 1").fetchone()
    return {"id": row[0], "customer_id": row[1], "outstanding": row[2] - row[3], "cancelled": cancelled}


@pytest.mark.parametrize("amount,when,why", [
    (0, None, "greater than 0"),
    (-500, None, "greater than 0"),
    (1000, (date.today() + timedelta(days=400)).isoformat(), "future"),
    (1000, "15-07-2026", "YYYY-MM-DD"),
])
def test_bad_payments_rejected(as_role, booking, amount, when, why):
    body = {"booking_id": booking["id"], "customer_id": booking["customer_id"], "amount": amount}
    if when:
        body["payment_date"] = when
    r = as_role("admin").post("/api/payments", json=body)
    assert r.status_code == 400 and why in r.json()["detail"]


def test_payment_over_outstanding_rejected(as_role, booking):
    r = as_role("admin").post("/api/payments", json={"booking_id": booking["id"], "customer_id": booking["customer_id"],
                                                     "amount": booking["outstanding"] + 1})
    assert r.status_code == 400 and "outstanding" in r.json()["detail"]


def test_payment_on_missing_or_cancelled_booking_rejected(as_role, booking):
    admin = as_role("admin")
    r = admin.post("/api/payments", json={"booking_id": 99999999, "customer_id": booking["customer_id"], "amount": 10})
    assert r.status_code == 400 and "not found" in r.json()["detail"]
    if booking["cancelled"]:
        bid, cid = booking["cancelled"]
        r = admin.post("/api/payments", json={"booking_id": bid, "customer_id": cid, "amount": 10})
        assert r.status_code == 400 and "active" in r.json()["detail"]


def test_payment_wrong_customer_rejected(as_role, booking):
    r = as_role("admin").post("/api/payments", json={"booking_id": booking["id"],
                                                     "customer_id": booking["customer_id"] + 100000, "amount": 10})
    assert r.status_code == 400 and "different customer" in r.json()["detail"]


def _fresh_unit(admin, world, suffix):
    r = admin.post("/api/units", json={"project_id": world["scoped_project"], "unit_no": f"VAL-{suffix}",
                                       "base_sale_price": 1_000_000})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_unit_cannot_be_marked_booked_without_booking(as_role, world):
    admin = as_role("admin")
    uid = _fresh_unit(admin, world, "A")
    for st in ("booked", "sold", "possession_delivered"):
        r = admin.put(f"/api/units/{uid}/status", json={"status": st})
        assert r.status_code == 400, st
    assert admin.post("/api/units", json={"project_id": world["scoped_project"], "unit_no": "VAL-SOLD",
                                          "status": "sold"}).status_code == 400


def test_booking_plan_must_cover_price(as_role, world):
    admin = as_role("admin")
    uid = _fresh_unit(admin, world, "B")
    cust = admin.post("/api/customers", json={"name": "Plan Test", "cnic": "99999-8888888-1"}).json()
    base = {"unit_id": uid, "project_id": world["scoped_project"], "customer_id": cust["id"],
            "sale_price": 1_000_000, "booking_amount": 200_000, "booking_date": "2026-01-10"}
    short = [{"amount": 200_000, "due_date": "2026-01-10"}, {"amount": 500_000, "due_date": "2026-02-10"}]
    r = admin.post("/api/bookings", json={**base, "installments": short})
    assert r.status_code == 400 and "short by PKR 300,000" in r.json()["detail"]
    r = admin.post("/api/bookings", json={**base, "booking_date": "10-01-2026",
                                          "installments": short + [{"amount": 300_000, "due_date": "2026-03-10"}]})
    assert r.status_code == 400 and "YYYY-MM-DD" in r.json()["detail"]
    # booking amount paid outside the plan is also valid
    r = admin.post("/api/bookings", json={**base, "installments": [{"amount": 800_000, "due_date": "2026-03-10"}]})
    assert r.status_code == 200, r.text


def test_template_expands_installment_count_from_booking_date(as_role, world):
    admin = as_role("admin")
    pid = admin.post("/api/projects", json={"name": "Template Expand", "status": "active"}).json()["id"]
    r = admin.put(f"/api/projects/{pid}/installment-template", json={"name": "M-18", "default_booking_bps": 2000, "rules": [
        {"label": "Monthly", "trigger_kind": "time", "amount_bps": 8750, "installment_count": 18,
         "start_offset_months": 1, "interval_months": 1},
        {"label": "Possession", "trigger_kind": "construction", "amount_bps": 1250, "milestone_progress": 100}]})
    assert r.status_code == 200, r.text
    pv = admin.post(f"/api/projects/{pid}/installment-template/preview",
                    json={"sale_price": 5_670_000, "booking_amount": 1_134_000, "booking_date": "2026-01-31"}).json()
    rows = pv["installments"]
    assert len(rows) == 19
    assert sum(x["amount"] for x in rows) == 5_670_000 - 1_134_000
    assert [x["due_date"] for x in rows[:3]] == ["2026-02-28", "2026-03-31", "2026-04-30"]
    assert rows[-1]["trigger_kind"] == "construction"


def test_project_create_rules(as_role):
    admin = as_role("admin")
    planning = admin.post("/api/projects", json={
        "name": "Plan Only", "location": "Lahore", "status": "planning",
        "current_progress": 40, "number_of_floors": 4, "number_of_units": 20})
    assert planning.status_code == 200, planning.text
    assert planning.json()["raw_status"] == "planning"
    assert planning.json()["progress"] == 0
    assert planning.json()["project_type"] == "building"

    done = admin.post("/api/projects", json={
        "name": "Finished Block", "location": "Lahore", "status": "completed",
        "current_progress": 10, "project_type": "building"})
    assert done.status_code == 200, done.text
    assert done.json()["progress"] == 100

    building = admin.post("/api/projects", json={
        "name": "Live Tower", "location": "Lahore", "status": "under_construction",
        "current_progress": 35, "number_of_floors": 8, "number_of_units": 40})
    assert building.status_code == 200, building.text
    assert building.json()["progress"] == 35

    scheme = admin.post("/api/projects", json={
        "name": "Green Valley", "location": "Multan", "project_type": "housing_scheme",
        "number_of_floors": 6, "number_of_units": 80})
    assert scheme.status_code == 200, scheme.text
    assert scheme.json()["project_type"] == "housing_scheme"
    assert scheme.json()["number_of_floors"] == 0

    bad_floors = admin.post("/api/projects", json={
        "name": "Too Many Floors", "location": "Lahore",
        "number_of_floors": 12, "number_of_units": 8})
    assert bad_floors.status_code == 400 and "floors" in bad_floors.json()["detail"]

    bad_type = admin.post("/api/projects", json={"name": "Plaza", "location": "X", "project_type": "plaza"})
    assert bad_type.status_code == 400


def test_unit_type_and_bulk_import(as_role, world):
    admin = as_role("admin")
    pid = admin.post("/api/projects", json={"name": "Type Check", "location": "Lahore"}).json()["id"]
    shop = admin.post("/api/units", json={"project_id": pid, "unit_no": "S-01", "unit_type": "Shop"})
    assert shop.status_code == 200, shop.text
    assert shop.json()["unit_type"] == "commercial" and shop.json()["type_label"] == "Commercial"
    house = admin.post("/api/units", json={"project_id": pid, "unit_no": "H-01", "unit_type": "House",
                                           "residential_type": "2 Bed Lounge"})
    assert house.status_code == 200
    assert house.json()["unit_type"] == "residential"
    bad = admin.post("/api/units", json={"project_id": pid, "unit_no": "X-01", "unit_type": "warehouse-x"})
    assert bad.status_code == 400
    bulk = admin.post("/api/units/bulk", json={"project_id": pid, "units": [
        {"unit_no": "A-201", "unit_type": "residential", "layout": "Studio", "floor_number": 2, "price": "2500000"},
        {"unit_no": "S-01", "unit_type": "commercial"},
        {"unit_no": "", "unit_type": "residential"},
    ]})
    assert bulk.status_code == 200, bulk.text
    assert bulk.json()["created"] == 1 and bulk.json()["failed"] == 2
    listed = admin.get(f"/api/units?project_id={pid}").json()
    assert {u["unit_no"] for u in listed} >= {"S-01", "H-01", "A-201"}


def test_demand_notice_explains_overdue(as_role):
    admin = as_role("admin")
    pid = admin.post("/api/projects", json={"name": "Demand Block", "location": "Lahore"}).json()["id"]
    cid = admin.post("/api/customers", json={"name": "Late Buyer", "cnic": "35202-1111111-1",
                                             "phone": "03001234567"}).json()["id"]
    uid = admin.post("/api/units", json={"project_id": pid, "unit_no": "D-01",
                                         "unit_type": "residential", "base_sale_price": 1_000_000}).json()["id"]
    booked = admin.post("/api/bookings", json={
        "customer_id": cid, "unit_id": uid, "project_id": pid,
        "booking_date": "2026-01-01", "sale_price": 1_000_000, "booking_amount": 100_000,
        "installments": [{"amount": 900_000, "due_date": "2026-02-01", "type": "Monthly"}],
    })
    assert booked.status_code == 200, booked.text
    notices = admin.get("/api/demand-notices").json()
    mine = [n for n in notices if n["unit_no"] == "D-01"]
    assert mine, notices
    n = mine[0]
    assert n["why"] and "due" in n["why"].lower()
    assert n["what"] and "900,000" in n["what"]
    assert n["when"] and "overdue" in n["when"].lower()
    rec = admin.get("/api/recovery").json()
    assert "due_soon" in rec
    assert any(x["unit_no"] == "D-01" for x in rec["overdue"])


def test_duplicate_partner_cnic_and_vendor_ntn_rejected(as_role, world):
    admin = as_role("admin")
    link = {"project_id": world["scoped_project"], "agreed_amount": 1000, "investment_date": "2026-01-01"}
    r = admin.post("/api/partners", json={"name": "P1", "cnic": "12345-0000000-9", **link})
    assert r.status_code == 200, r.text
    r = admin.post("/api/partners", json={"name": "P2", "cnic": "12345-0000000-9", **link})
    assert r.status_code == 400 and "CNIC" in r.json()["detail"]
    assert admin.post("/api/vendors", json={"name": "V1", "ntn": "NTN-777"}).status_code == 200
    r = admin.post("/api/vendors", json={"name": "V2", "ntn": "NTN-777"})
    assert r.status_code == 400 and "NTN" in r.json()["detail"]


def test_cashbook_entry_cash_or_bank(as_role):
    admin = as_role("admin")
    before = {a["code"]: a for a in admin.get("/api/reports/trial-balance").json()["accounts"]}
    r = admin.post("/api/ledger", json={"entry_date": date.today().isoformat(), "narration": "petty cash",
                                        "amount": 7_000, "direction": "out", "payment_method": "Cash"})
    assert r.status_code == 200, r.text
    after = {a["code"]: a for a in admin.get("/api/reports/trial-balance").json()["accounts"]}
    bal = lambda d, c: (d.get(c, {}).get("debit", 0) - d.get(c, {}).get("credit", 0))
    assert bal(after, "1010") - bal(before, "1010") == -7_000
    assert bal(after, "1020") == bal(before, "1020")
    assert admin.post("/api/ledger", json={"entry_date": "01-06-2026", "narration": "x", "amount": 5,
                                           "direction": "out"}).status_code == 400


def test_opening_and_current_balance(as_role):
    admin = as_role("admin")
    before = admin.get("/api/ledger").json()
    cash0, bank0 = before["cash"], before["bank"]
    r = admin.put("/api/ledger/balance", json={
        "cash": cash0 + 25_000, "bank": bank0 + 100_000,
        "as_of": date.today().isoformat(), "reason": "Till count",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cash"] == cash0 + 25_000
    assert body["bank"] == bank0 + 100_000
    assert body["current"] == cash0 + bank0 + 125_000
    tb = admin.get("/api/reports/trial-balance").json()
    assert tb["balanced"] is True
    equity = next(a for a in tb["accounts"] if a["code"] == "3200")
    assert equity["credit"] >= 125_000
    same = admin.put("/api/ledger/balance", json={"cash": body["cash"], "bank": body["bank"]})
    assert same.status_code == 400

    pid = admin.post("/api/projects", json={"name": "Cash Site", "location": "Lahore"}).json()["id"]
    admin.post("/api/ledger", json={
        "entry_date": date.today().isoformat(), "narration": "Site petty", "amount": 1_000,
        "direction": "out", "payment_method": "Cash", "project_id": pid,
    })
    scoped = admin.get(f"/api/ledger?project_id={pid}").json()
    assert scoped["filtered"] is True
    assert scoped["outflow"] >= 1_000
    assert all(e.get("project_id") == pid for e in scoped["entries"])


def test_company_opening_balance_is_optional(as_role):
    sa = as_role("superadmin")
    plan = sa.get("/api/console/plans").json()[0]
    skip = sa.post("/api/console/companies", json={
        "name": "Zero Start Co", "plan_id": plan["id"],
        "admin_name": "Zed", "admin_email": "zed@zerostart.test",
    })
    assert skip.status_code == 200, skip.text
    with_bal = sa.post("/api/console/companies", json={
        "name": "Cash Start Co", "plan_id": plan["id"],
        "admin_name": "Cash Owner", "admin_email": "owner@cashstart.test",
        "record_opening_balance": True, "opening_cash": 40_000, "opening_bank": 210_000,
        "opening_date": date.today().isoformat(),
    })
    assert with_bal.status_code == 200, with_bal.text
    owner = as_role(None)
    login(owner, "owner@cashstart.test", with_bal.json()["temporary_password"])
    owner.post("/api/auth/change-password", json={
        "current_password": with_bal.json()["temporary_password"], "new_password": "Quartz-Lamp-4822"})
    books = owner.get("/api/ledger").json()
    assert books["cash"] == 40_000 and books["bank"] == 210_000
    assert books["has_opening"] is True
    tb = owner.get("/api/reports/trial-balance").json()
    assert tb["balanced"] is True


def _po_setup(admin):
    pid = admin.post("/api/projects", json={"name": "PO Yard", "location": "Lahore"}).json()["id"]
    vid = admin.post("/api/vendors", json={"name": "Cement House"}).json()["id"]
    return pid, vid


def test_po_pack_units_grn_and_cancel_fee(as_role):
    admin = as_role("admin")
    pid, vid = _po_setup(admin)
    po = admin.post("/api/purchase-orders", json={
        "vendor_id": vid, "project_id": pid, "material": "Ordinary Portland Cement",
        "pack_qty": 2, "pack_size": 10, "pack_unit": "kg", "unit_cost": 1200, "total": 2400,
        "order_date": date.today().isoformat(),
    })
    assert po.status_code == 200, po.text
    body = po.json()
    assert body["total_units"] == 20
    assert "2" in body["qty_label"] and "10" in body["qty_label"] and "20" in body["qty_label"]
    assert body["status"] == "draft"
    po_id = body["id"]

    assert admin.put(f"/api/purchase-orders/{po_id}/status", json={"status": "approved"}).status_code == 200
    grn = admin.put(f"/api/purchase-orders/{po_id}/status", json={"status": "grn"})
    assert grn.status_code == 200, grn.text
    assert grn.json()["status"] == "payment_pending"
    stock = admin.get("/api/inventory").json()
    cement = next(i for i in stock if i["name"] == "Ordinary Portland Cement")
    assert cement["on_hand"] == 20
    assert cement["unit"] == "kg"

    pay = admin.post("/api/vendor-payments", json={
        "vendor_id": vid, "purchase_order_id": po_id, "amount": 2400,
        "payment_date": date.today().isoformat(),
    })
    assert pay.status_code == 200, pay.text

    blocked = admin.put(f"/api/purchase-orders/{po_id}/status", json={"status": "cancelled"})
    assert blocked.status_code == 400 and "cancel_fee_pct" in blocked.json()["detail"]

    preview = admin.get(f"/api/purchase-orders/{po_id}/cancel-preview")
    assert preview.status_code == 200
    assert preview.json()["needs_confirm"] is True
    assert preview.json()["suggested_fee"] == 720
    assert preview.json()["suggested_refund"] == 1680

    cancelled = admin.put(f"/api/purchase-orders/{po_id}/status", json={
        "status": "cancelled", "cancel_fee_pct": 30, "cancel_reason": "Wrong grade",
    })
    assert cancelled.status_code == 200, cancelled.text
    out = cancelled.json()
    assert out["status"] == "cancelled"
    assert out["cancel_fee_amount"] == 720
    assert out["cancel_refund_amount"] == 1680
    assert out["remaining"] == 0
    cement2 = admin.get(f"/api/inventory/{cement['id']}").json()
    assert cement2["on_hand"] == 0

    unpaid = admin.post("/api/purchase-orders", json={
        "vendor_id": vid, "project_id": pid, "material": "Sample paint", "total": 50_000,
        "order_date": date.today().isoformat(),
    })
    assert unpaid.status_code == 200
    ok = admin.put(f"/api/purchase-orders/{unpaid.json()['id']}/status", json={"status": "cancelled"})
    assert ok.status_code == 200 and ok.json()["status"] == "cancelled"


def test_contractor_and_site_log_details(as_role):
    admin = as_role("admin")
    pid = admin.post("/api/projects", json={"name": "Site Block", "location": "Lahore"}).json()["id"]
    ctr = admin.post("/api/contractors", json={
        "name": "Imran Mason", "company_name": "Imran & Sons", "father_name": "Bashir",
        "cnic": "35202-2222222-2", "contact": "03001112222", "emergency_contact": "03003334444",
        "email": "imran@sons.pk", "address": "Multan Road", "city": "Lahore",
        "ntn": "CTR-NTN-1", "pec_no": "CIVIL-123", "specialty": "Civil",
        "bank_name": "HBL", "account_title": "Imran & Sons", "account_no": "PK00HBL0001",
    })
    assert ctr.status_code == 200, ctr.text
    got = admin.get(f"/api/contractors/{ctr.json()['id']}").json()
    assert got["company_name"] == "Imran & Sons"
    assert got["pec_no"] == "CIVIL-123"
    assert got["city"] == "Lahore"

    log = admin.post("/api/site-logs", json={
        "project_id": pid, "log_date": date.today().isoformat(), "engineer": "Eng. Ali",
        "reporter": "Site clerk Farah", "time_from": "08:00", "time_to": "17:00",
        "workers_skilled": 4, "workers_unskilled": 12, "workforce_notes": "2 masons overtime",
        "work_done": "Ground floor columns", "extra_expenses": 3500,
        "expense_notes": "Diesel for mixer", "notes": "Light rain after 4pm",
        "materials": [{"name": "Cement", "qty": 8, "unit": "bags"}, {"name": "Sand", "qty": 1, "unit": "trolley"}],
    })
    assert log.status_code == 200, log.text
    row = log.json()
    assert row["hours_worked"] == 9
    assert row["reporter"] == "Site clerk Farah"
    assert row["extra_expenses"] == 3500
    assert any(m["name"] == "Cement" for m in row["materials"])
    assert "8 bags" in row["material_used"]

    up = admin.post(f"/api/site-logs/{row['id']}/attachments",
                    files=[("files", ("column.jpg", b"\xff\xd8\xfffakejpeg", "image/jpeg"))])
    assert up.status_code == 200, up.text
    atts = up.json()["attachments"]
    assert len(atts) == 1 and atts[0]["kind"] == "photo"
    dl = admin.get(f"/api/site-logs/{row['id']}/attachments/{atts[0]['id']}")
    assert dl.status_code == 200
    assert admin.delete(f"/api/site-logs/{row['id']}/attachments/{atts[0]['id']}").status_code == 200
    assert admin.get(f"/api/site-logs/{row['id']}").json()["attachments"] == []


def test_agent_commission_percent_flat_and_over_base(as_role, world):
    admin = as_role("admin")
    pid = world["scoped_project"]

    def book(n, sale, base, agent_id, extra=None):
        uid = admin.post("/api/units", json={"project_id": pid, "unit_no": f"STK-{n}",
                                             "base_sale_price": base}).json()["id"]
        cid = admin.post("/api/customers", json={"name": f"Stk Buyer {n}",
                                                 "cnic": f"35111-{n:07d}-1"}).json()["id"]
        body = {
            "customer_id": cid, "unit_id": uid, "project_id": pid, "sale_price": sale,
            "base_sale_price": base, "booking_amount": 100_000, "booking_date": "2026-03-01",
            "agent_id": agent_id,
            "installments": [{"amount": sale - 100_000, "due_date": "2026-04-01", "type": "Monthly"}],
        }
        if extra:
            body.update(extra)
        r = admin.post("/api/bookings", json=body)
        assert r.status_code == 200, r.text
        return admin.get(f"/api/agents/{agent_id}").json()["commissions"][0]

    pct = admin.post("/api/agents", json={"name": "Pct Deal", "commission_mode": "percent",
                                          "default_rate_pct": 2}).json()
    row = book(1, 1_000_000, 1_000_000, pct["id"])
    assert row["mode"] == "percent" and row["commission_amount"] == 20_000

    flat = admin.post("/api/agents", json={"name": "Flat Deal", "commission_mode": "flat",
                                           "default_flat_amount": 150_000}).json()
    row = book(2, 2_000_000, 1_800_000, flat["id"])
    assert row["mode"] == "flat" and row["commission_amount"] == 150_000

    over = admin.post("/api/agents", json={"name": "Over Base Deal", "commission_mode": "over_base",
                                           "over_base_pct": 100}).json()
    row = book(3, 1_200_000, 1_000_000, over["id"])
    assert row["mode"] == "over_base" and row["surplus"] == 200_000 and row["commission_amount"] == 200_000
    row = book(4, 900_000, 1_000_000, over["id"])
    assert row["commission_amount"] == 0 and row["surplus"] == 0

    row = book(5, 1_000_000, 1_000_000, pct["id"],
               {"commission_mode": "flat", "commission_flat_amount": 50_000})
    assert row["mode"] == "flat" and row["commission_amount"] == 50_000


def test_partner_no_monthly_return_and_occasion_payout(as_role, world):
    admin = as_role("admin")
    link = {"project_id": world["scoped_project"], "agreed_amount": 5000, "investment_date": "2026-01-01"}
    r = admin.post("/api/partners", json={
        "name": "No Monthly", "cnic": "11111-3333333-1", "partner_type": "Monthly Return",
        "monthly_return_pct": 2, **link,
    })
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["partner_type"] == "Profit Sharing"
    assert p["monthly_return_pct"] is None
    assert p["accrued_return"] == 0
    assert p["return_due"] == 0

    r = admin.post("/api/partners", json={
        "name": "Share Partner", "cnic": "11111-3333333-2", "profit_share_pct": 15,
        "profit_share_basis": "milestone", **link,
    })
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["profit_share_basis"] == "milestone"
    pid = p["id"]
    assert admin.post(f"/api/partners/{pid}/contribute",
                      json={"amount": 5000, "contribution_date": "2026-01-02"}).status_code == 200
    d = admin.post(f"/api/partners/{pid}/distribute", json={
        "amount": 800, "distribution_date": "2026-06-01", "occasion": "milestone",
    })
    assert d.status_code == 200, d.text
    assert d.json()["distributions"][0]["occasion"] == "milestone"


def test_parties_search_by_cnic_and_phone(as_role):
    admin = as_role("admin")
    admin.post("/api/customers", json={"name": "Find Me Party", "cnic": "42201-9988776-5",
                                       "phone": "03001112233"})
    rows = admin.get("/api/entities", params={"q": "42201-9988776-5"}).json()
    assert any(r["name"] == "Find Me Party" for r in rows)
    rows = admin.get("/api/entities", params={"q": "03001112233"}).json()
    assert any(r["name"] == "Find Me Party" for r in rows)
    rows = admin.get("/api/entities", params={"q": "CUS-", "type": "customer"}).json()
    assert any(r["entity_type"] == "customer" for r in rows)


