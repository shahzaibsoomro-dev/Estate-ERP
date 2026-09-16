"""Input validation found while importing a real workbook."""
from datetime import date, timedelta

import pytest


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
