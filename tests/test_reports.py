"""Report centre endpoints."""
import pytest

ENDPOINTS = ["overview", "ageing", "sales", "sales-summary", "collections", "inventory",
             "customer-balances", "payables", "budget"]


@pytest.mark.parametrize("name", ENDPOINTS)
def test_reports_load_for_admin(as_role, name):
    admin = as_role("admin")
    r = admin.get(f"/api/reports/{name}")
    assert r.status_code == 200, r.text
    r = admin.get(f"/api/reports/{name}?date_from=2024-01-01&date_to=2030-12-31")
    assert r.status_code == 200, r.text


def test_invalid_dates_rejected(as_role):
    admin = as_role("admin")
    assert admin.get("/api/reports/collections?date_from=15-01-2026").status_code == 400


def test_project_filter_narrows_results(as_role, world):
    admin = as_role("admin")
    p = world["scoped_project"]
    inv = admin.get(f"/api/reports/inventory?project_ids={p}").json()
    assert [row["project_id"] for row in inv["by_project"]] == [p]
    ageing = admin.get(f"/api/reports/ageing?project_ids={p}").json()
    assert all(row["project_id"] == p for row in ageing["by_project"])


def test_ageing_buckets_add_up(as_role):
    d = as_role("admin").get("/api/reports/ageing").json()
    assert round(sum(b["amount"] for b in d["buckets"]), 2) == round(d["total"], 2)
    assert round(sum(i["amount"] for i in d["items"]), 2) == round(d["total"], 2)


def test_reports_permissions(as_role):
    # A read-only employee with every project can see reports.
    assert as_role("employee_all").get("/api/reports/overview").status_code == 200
    # Company-wide reports need all-project access and the reports right.
    assert as_role("employee_scoped").get("/api/reports/overview").status_code == 403
    assert as_role("customer").get("/api/reports/overview").status_code == 403
    assert as_role(None).get("/api/reports/overview").status_code == 401


def test_reports_are_company_isolated(as_role):
    d = as_role("admin_b").get("/api/reports/overview").json()
    assert d["bookings"] == 0 and d["collections"] == 0


ACCOUNTING = ["trial-balance", "general-ledger", "general-ledger?account=1100", "balance-sheet",
              "expense-ledger", "monthly", "project-wise", "audit"]


@pytest.mark.parametrize("name", ACCOUNTING)
def test_accounting_reports_load(as_role, name):
    r = as_role("admin").get(f"/api/reports/{name}")
    assert r.status_code == 200, r.text


def test_books_balance(as_role, world):
    admin = as_role("admin")
    for q in ("", f"?project_ids={world['scoped_project']}", "?date_to=2025-06-30"):
        tb = admin.get(f"/api/reports/trial-balance{q}").json()
        assert tb["balanced"] and tb["total_debit"] == tb["total_credit"]
        bs = admin.get(f"/api/reports/balance-sheet{q}").json()
        assert bs["balanced"]
        assert bs["total_assets"] == bs["total_liabilities"] + bs["total_equity"]


def test_general_ledger_running_balance(as_role):
    d = as_role("admin").get("/api/reports/general-ledger?account=1100&date_from=2025-01-01").json()
    bal = d["opening"]
    for line in d["lines"]:
        bal += line["debit"] - line["credit"]  # receivables are debit-normal
        assert line["balance"] == bal
    closing = next(a for a in d["accounts"] if a["code"] == "1100")["closing"]
    assert bal == closing


def test_monthly_cash_matches_balance_sheet(as_role):
    admin = as_role("admin")
    m = admin.get("/api/reports/monthly").json()
    bs = admin.get("/api/reports/balance-sheet?date_to=2999-12-31").json()
    cash = sum(a["amount"] for a in bs["assets"] if a["group"] == "Cash & bank")
    assert m["closing"] == cash
    assert m["opening"] + m["total_in"] - m["total_out"] == m["closing"]


def test_unknown_account_rejected(as_role):
    assert as_role("admin").get("/api/reports/general-ledger?account=9999").status_code == 400


def test_audit_checks_present(as_role):
    d = as_role("admin").get("/api/reports/audit").json()
    assert d["checks"] and all({"check", "ok", "detail"} <= set(c) for c in d["checks"])
    assert d["checks"][0]["ok"]  # journal always balances


def test_new_company_has_empty_books(as_role):
    tb = as_role("admin_b").get("/api/reports/trial-balance").json()
    assert tb["accounts"] == [] and tb["balanced"]


def test_dashboard_and_recovery_ignore_cancelled_bookings(as_role, world):
    from backend.database import get_db
    admin = as_role("admin")
    with get_db(world["a_db"]) as conn:
        open_cancelled = conn.execute(
            """SELECT COALESCE(SUM(i.remaining_amount),0) FROM installments i JOIN bookings b ON b.id=i.booking_id
               WHERE b.status='cancelled' AND i.status IN ('pending','partial','overdue')""").fetchone()[0]
        open_active = conn.execute(
            """SELECT COALESCE(SUM(i.remaining_amount),0) FROM installments i JOIN bookings b ON b.id=i.booking_id
               WHERE b.status='active' AND i.status IN ('pending','partial','overdue')""").fetchone()[0]
    dash = admin.get("/api/dashboard").json()
    rec = admin.get("/api/recovery").json()
    ageing = admin.get("/api/reports/ageing").json()
    assert dash["kpi"]["receivable"] == open_active == rec["receivable"]
    assert rec["overdue_amt"] == ageing["total"] == sum(x["amount"] for x in dash["overdue"])
    assert open_cancelled == 0 or dash["kpi"]["receivable"] != open_active + open_cancelled


def test_payables_count_vendor_advances(as_role, world):
    from backend.database import get_db
    admin = as_role("admin")
    with get_db(world["a_db"]) as conn:
        total_paid = conn.execute("SELECT COALESCE(SUM(amount),0) FROM vendor_payments").fetchone()[0]
    pay = admin.get("/api/reports/payables").json()
    assert pay["totals"]["vendor_paid"] == total_paid
    tb = {a["code"]: a for a in admin.get("/api/reports/trial-balance").json()["accounts"]}
    assert tb["2000"]["credit"] - tb["2000"]["debit"] == pay["totals"]["vendor_balance"]


def test_project_wise_progress_uses_project_progress(as_role, world):
    from backend.database import get_db
    with get_db(world["a_db"]) as conn:
        raw = {r[0]: r[1] or 0 for r in conn.execute("SELECT id, current_progress FROM projects")}
    d = as_role("admin").get("/api/reports/project-wise").json()
    assert {p["project_id"]: p["progress"] for p in d["projects"]} == raw


def test_cancel_never_forfeits_more_than_paid(as_role, world):
    from backend.database import get_db
    admin = as_role("admin")
    with get_db(world["a_db"]) as conn:
        rows = conn.execute(
            """SELECT b.id, b.booking_amount, COALESCE((SELECT SUM(amount) FROM payments p WHERE p.booking_id=b.id),0)
               FROM bookings b WHERE b.status='active'""").fetchall()
    assert rows
    for bid, booking_amount, paid in rows:
        p = admin.get(f"/api/bookings/{bid}/cancel-preview").json()
        assert p["forfeit_amount"] <= paid
        assert p["forfeit_amount"] + p["refund_amount"] == paid
