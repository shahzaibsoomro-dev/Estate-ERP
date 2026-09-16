"""Read-only data audit: connection, integrity, consistency, and report reconciliation.

Usage: python3 check_data.py <project_dir> <work_dir> <admin_email> <admin_password>
Copies the databases into <work_dir> first, so the real files are never modified.
"""
import json
import os
import shutil
import sqlite3
import sys
from datetime import date

proj, work, email, password = sys.argv[1:5]
os.makedirs(work, exist_ok=True)
for f in ("haven.db", "platform.db"):
    shutil.copy(os.path.join(proj, "db", f), os.path.join(work, f))
os.environ["ERP_DB_PATH"] = os.path.join(work, "haven.db")
os.environ["ERP_PLATFORM_DB_PATH"] = os.path.join(work, "platform.db")
os.environ["ERP_TENANTS_DIR"] = os.path.join(work, "tenants")
sys.path.insert(0, proj)

results = []  # (section, check, ok, detail)


def check(section, name, ok, detail=""):
    results.append((section, name, bool(ok), str(detail)))


db = sqlite3.connect(os.path.join(work, "haven.db"))
db.row_factory = sqlite3.Row
q = lambda sql, *a: db.execute(sql, a).fetchall()
one = lambda sql, *a: db.execute(sql, a).fetchone()[0]
TODAY = date.today().isoformat()

# ------------------------------------------------------------------ 1. connection
from backend import config  # noqa: E402
from backend.saas.service import resolve_db_path  # noqa: E402

plat = sqlite3.connect(os.path.join(work, "platform.db"))
companies = plat.execute("SELECT id, name, db_path, status FROM companies").fetchall()
S = "1. Connection"
check(S, "Platform DB has companies", companies, companies)
for cid, name, path, status in companies:
    real = os.path.join(proj, path) if not os.path.isabs(path) else path
    check(S, f"Company '{name}' database file exists", os.path.exists(real), path)
check(S, "Company DB opens and passes integrity_check", one("PRAGMA integrity_check") == "ok")
check(S, "No broken foreign keys", not q("PRAGMA foreign_key_check"))
check(S, "Platform DB passes integrity_check", plat.execute("PRAGMA integrity_check").fetchone()[0] == "ok")
orphan_users = plat.execute("""SELECT email FROM users WHERE role != 'superadmin'
                               AND company_id NOT IN (SELECT id FROM companies)""").fetchall()
check(S, "Every user belongs to an existing company", not orphan_users, orphan_users)

# ------------------------------------------------------------------ 2. consistency
S = "2. Data consistency"
bad = q("SELECT id FROM installments WHERE status != 'cancelled' AND amount != paid_amount + remaining_amount")
check(S, "Installment amount = paid + remaining (live installments)", not bad, f"{len(bad)} rows: {[r[0] for r in bad[:10]]}")
bad = q("""SELECT b.booking_no, b.status, b.booking_amount,
                  (SELECT COALESCE(SUM(paid_amount),0) FROM installments WHERE booking_id=b.id) ip,
                  (SELECT COALESCE(SUM(amount),0) FROM payments WHERE booking_id=b.id) pp,
                  EXISTS (SELECT 1 FROM installments WHERE booking_id=b.id AND type='Booking') has_bk
           FROM bookings b WHERE b.status='active'""")
bad = [r for r in bad if r["pp"] != r["ip"] + (0 if r["has_bk"] else min(r["booking_amount"] or 0, r["pp"]))]
check(S, "Per booking: payments = installment paid amounts (+ booking amount paid outside the plan)", not bad,
      ", ".join(f"{r['booking_no']} payments {r['pp']:,} vs plan paid {r['ip']:,}" for r in bad[:6]))
bad = q("SELECT id FROM installments WHERE status='paid' AND remaining_amount > 0")
check(S, "Installments marked paid have nothing remaining", not bad, len(bad))
bad = q("SELECT id FROM installments WHERE remaining_amount = 0 AND amount > 0 AND status NOT IN ('paid','cancelled')")
check(S, "Fully paid installments are marked paid", not bad, [r[0] for r in bad[:10]])
bad = q("""SELECT b.booking_no, b.final_sale_price, SUM(i.amount) s, b.booking_amount,
                  SUM(CASE WHEN i.type='Booking' THEN 1 ELSE 0 END) has_bk
           FROM bookings b JOIN installments i ON i.booking_id=b.id
           WHERE b.status='active' GROUP BY b.id""")
bad = [r for r in bad if r[2] + (0 if r[4] else (r[3] or 0)) != r[1]]
short = sum(r[1] - r[2] - (0 if r[4] else (r[3] or 0)) for r in bad)
check(S, "Active booking: payment plan covers the full sale price", not bad,
      f"{len(bad)} bookings, PKR {short:,} not scheduled. e.g. " + ", ".join(f"{r[0]} plan {r[2]:,} vs price {r[1]:,}" for r in bad[:5]))
bad = q("SELECT b.booking_no FROM bookings b WHERE b.status='active' AND NOT EXISTS (SELECT 1 FROM installments i WHERE i.booking_id=b.id)")
check(S, "Every active booking has a payment plan", not bad, [r[0] for r in bad])
bad = q("SELECT b.booking_no FROM bookings b JOIN units u ON u.id=b.unit_id WHERE b.project_id != u.project_id")
check(S, "Booking project matches its unit's project", not bad, [r[0] for r in bad])
bad = q("""SELECT u.id, COUNT(*) FROM bookings b JOIN units u ON u.id=b.unit_id WHERE b.status='active'
           GROUP BY u.id HAVING COUNT(*) > 1""")
check(S, "No unit has two active bookings", not bad, bad)
bad = q("""SELECT u.unit_no, u.status FROM units u JOIN bookings b ON b.unit_id=u.id AND b.status='active'
           WHERE u.status NOT IN ('booked','sold','possession_delivered')""")
check(S, "Units with an active booking are booked/sold", not bad, [tuple(r) for r in bad[:10]])
bad = q("""SELECT u.unit_no, u.status, p.name FROM units u JOIN projects p ON p.id=u.project_id
           WHERE u.status IN ('booked','sold','possession_delivered')
             AND NOT EXISTS (SELECT 1 FROM bookings b WHERE b.unit_id=u.id AND b.status='active')""")
by_proj = {}
for r in bad:
    by_proj[r[2]] = by_proj.get(r[2], 0) + 1
check(S, "Units marked booked/sold have an active booking", not bad,
      f"{len(bad)} units without a booking: {by_proj}")
bad = q("""SELECT u.unit_no FROM units u WHERE u.status='hold'
           AND NOT EXISTS (SELECT 1 FROM unit_holds h WHERE h.unit_id=u.id AND h.status='active')""")
check(S, "Units on hold have an active hold record", not bad, f"{len(bad)}: {[r[0] for r in bad[:10]]}")
bad = q("SELECT id FROM payments p WHERE p.booking_id IS NOT NULL AND p.customer_id != (SELECT customer_id FROM bookings WHERE id=p.booking_id)")
xfer = one("SELECT COUNT(*) FROM booking_transfers")
check(S, "Payment customer matches booking customer (except transferred bookings)",
      len(bad) <= xfer * 50, f"{len(bad)} payments differ; {xfer} transfers on record")
bad = q("SELECT id FROM payments WHERE amount <= 0")
check(S, "No zero/negative payments", not bad, len(bad))
bad = q("SELECT id FROM payments WHERE payment_date > ?", TODAY)
check(S, "No payments dated in the future", not bad, len(bad))
bad = q("SELECT p.id FROM payments p WHERE NOT EXISTS (SELECT 1 FROM receipts r WHERE r.payment_id=p.id)")
check(S, "Every payment has a receipt", not bad, len(bad))
dup = q("SELECT receipt_no, COUNT(*) FROM receipts GROUP BY receipt_no HAVING COUNT(*) > 1")
check(S, "Receipt numbers are unique", not dup, dup)
dup = q("SELECT booking_no, COUNT(*) FROM bookings GROUP BY booking_no HAVING COUNT(*) > 1")
check(S, "Booking numbers are unique", not dup, dup)
bad = q("""SELECT b.booking_no, bc.total_paid, COALESCE((SELECT SUM(amount) FROM payments p WHERE p.booking_id=b.id),0) s
           FROM booking_cancellations bc JOIN bookings b ON b.id=bc.booking_id
           WHERE bc.total_paid != COALESCE((SELECT SUM(amount) FROM payments p WHERE p.booking_id=b.id),0)""")
check(S, "Cancellation 'total paid' matches payments on that booking", not bad,
      f"{len(bad)}: " + ", ".join(f"{r[0]} says {r[1]:,}, payments {r[2]:,}" for r in bad[:5]))
bad = q("""SELECT b.booking_no, bc.total_paid, bc.forfeit_amount, bc.refund_amount FROM booking_cancellations bc
           JOIN bookings b ON b.id=bc.booking_id WHERE bc.forfeit_amount + bc.refund_amount != bc.total_paid""")
check(S, "Cancellation: forfeit + refund = total paid", not bad,
      f"{len(bad)}: " + ", ".join(f"{r[0]} paid {r[1]:,} forfeit {r[2]:,} refund {r[3]:,}" for r in bad[:5]))
bad = q("""SELECT COUNT(*), COALESCE(SUM(i.remaining_amount),0) FROM installments i JOIN bookings b ON b.id=i.booking_id
           WHERE b.status='cancelled' AND i.status NOT IN ('cancelled','paid') AND i.remaining_amount > 0""")[0]
check(S, "Cancelled bookings have no open installments", not bad[0], f"{bad[0]} open, PKR {bad[1]:,}")
bad = q("SELECT b.booking_no FROM bookings b WHERE b.status='cancelled' AND NOT EXISTS (SELECT 1 FROM booking_cancellations c WHERE c.booking_id=b.id)")
check(S, "Every cancelled booking has a cancellation record", not bad, [r[0] for r in bad])
bad = q("SELECT po_no, quantity, unit_cost, total FROM purchase_orders WHERE quantity * unit_cost != total")
check(S, "Purchase order total = quantity x unit cost", not bad, [tuple(r) for r in bad])
bad = q("""SELECT po.po_no, po.total, SUM(vp.amount) FROM purchase_orders po JOIN vendor_payments vp ON vp.purchase_order_id=po.id
           GROUP BY po.id HAVING SUM(vp.amount) > po.total""")
check(S, "No purchase order is overpaid", not bad, [tuple(r) for r in bad])
bad = q("""SELECT vp.id, po.po_no FROM vendor_payments vp JOIN purchase_orders po ON po.id=vp.purchase_order_id
           WHERE po.status='cancelled'""")
check(S, "No payments on cancelled purchase orders", not bad, [tuple(r) for r in bad])
bad = q("""SELECT ac.id, ac.paid_amount, COALESCE((SELECT SUM(amount) FROM agent_commission_payments p WHERE p.commission_id=ac.id),0)
           FROM agent_commissions ac
           WHERE ac.paid_amount != COALESCE((SELECT SUM(amount) FROM agent_commission_payments p WHERE p.commission_id=ac.id),0)""")
check(S, "Commission paid_amount = commission payments", not bad, [tuple(r) for r in bad])
bad = q("SELECT id FROM agent_commissions WHERE paid_amount > commission_amount")
check(S, "No commission paid above the amount earned", not bad, [r[0] for r in bad])
bad = q("""SELECT ac.id, ac.status, ac.paid_amount FROM agent_commissions ac WHERE
           (ac.status='paid' AND ac.paid_amount < ac.commission_amount) OR
           (ac.status='earned' AND ac.paid_amount > 0) OR
           (ac.status='reversed' AND ac.paid_amount > 0)""")
check(S, "Commission status matches what was paid", not bad, [tuple(r) for r in bad])
bad = q("SELECT id, name, status FROM projects WHERE COALESCE(current_progress,0) < 0 OR COALESCE(current_progress,0) > 100")
check(S, "Project progress is between 0 and 100", not bad, [tuple(r) for r in bad])
bad = q("SELECT p.name, p.number_of_units, (SELECT COUNT(*) FROM units u WHERE u.project_id=p.id) c FROM projects p WHERE p.number_of_units IS NOT NULL AND p.number_of_units != (SELECT COUNT(*) FROM units u WHERE u.project_id=p.id)")
check(S, "Project 'number of units' matches units created", not bad,
      ", ".join(f"{r[0]}: says {r[1]}, has {r[2]}" for r in bad))
bad = q("SELECT c.id, c.name FROM customers c WHERE c.cnic IS NULL OR TRIM(c.cnic)=''")
check(S, "Every customer has a CNIC", not bad, [tuple(r) for r in bad[:10]])
dup = q("SELECT cnic, COUNT(*) FROM customers WHERE cnic IS NOT NULL AND cnic != '' GROUP BY cnic HAVING COUNT(*) > 1")
check(S, "Customer CNICs are unique", not dup, dup)

# ------------------------------------------------------------------ 3. reports vs raw database
from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402

S = "3. Reports match the database"
client = TestClient(app)
client.__enter__()
r = client.post("/api/auth/login", json={"identifier": email, "password": password})
check(S, f"Sign in as {email}", r.status_code == 200, r.text[:200] if r.status_code != 200 else "")
if r.status_code != 200:
    raise SystemExit(json.dumps(results, indent=1))
get = lambda path: client.get(path).json()
# refresh_statuses runs inside the reports; re-read after the first call
get("/api/reports/overview")
db = sqlite3.connect(os.path.join(work, "haven.db"))
q = lambda sql, *a: db.execute(sql, a).fetchall()
one = lambda sql, *a: db.execute(sql, a).fetchone()[0]


def eq(name, report_value, raw_value, section=S):
    check(section, name, report_value == raw_value, f"report {report_value:,} / database {raw_value:,}"
          if isinstance(report_value, (int, float)) and isinstance(raw_value, (int, float))
          else f"report {report_value} / database {raw_value}")


ov = get("/api/reports/overview")
eq("Overview · collections (all time)", ov["collections"], one("SELECT COALESCE(SUM(amount),0) FROM payments WHERE booking_id IS NOT NULL"))
eq("Overview · active bookings", ov["bookings"], one("SELECT COUNT(*) FROM bookings WHERE status='active'"))
eq("Overview · active sales value", ov["sales_value"], one("SELECT COALESCE(SUM(final_sale_price),0) FROM bookings WHERE status='active'"))
eq("Overview · available units", ov["available_units"], one("SELECT COUNT(*) FROM units WHERE status='available'"))
eq("Overview · overdue", ov["overdue"], one("""SELECT COALESCE(SUM(i.remaining_amount),0) FROM installments i JOIN bookings b ON b.id=i.booking_id
    WHERE b.status='active' AND i.status IN ('overdue','partial') AND i.remaining_amount>0 AND i.due_date < date('now')"""))

ag = get("/api/reports/ageing")
eq("Ageing · total overdue = overview overdue", ag["total"], ov["overdue"])
eq("Ageing · buckets add up", sum(b["amount"] for b in ag["buckets"]), ag["total"])
eq("Ageing · customers add up", sum(c["amount"] for c in ag["by_customer"]), ag["total"])

co = get("/api/reports/collections")
eq("Collections · total", co["total"], one("SELECT COALESCE(SUM(p.amount),0) FROM payments p JOIN bookings b ON b.id=p.booking_id"))
eq("Collections · by method adds up", sum(m["amount"] for m in co["by_method"]), co["total"])
eq("Collections · by project adds up", sum(m["amount"] for m in co["by_project"]), co["total"])
eq("Collections · by month adds up", sum(m["amount"] for m in co["monthly"]), co["total"])

ss = get("/api/reports/sales-summary")
eq("Sales · bookings", sum(p["bookings"] for p in ss["by_project"]), one("SELECT COUNT(*) FROM bookings WHERE status='active'"))
eq("Sales · value", sum(p["sales_value"] for p in ss["by_project"]), one("SELECT SUM(final_sale_price) FROM bookings WHERE status='active'"))
eq("Sales · collected on active bookings", sum(p["collected"] for p in ss["by_project"]),
   one("SELECT COALESCE(SUM(p.amount),0) FROM payments p JOIN bookings b ON b.id=p.booking_id WHERE b.status='active'"))
eq("Sales · cancelled count", ss["cancelled"], one("SELECT COUNT(*) FROM bookings WHERE status='cancelled'"))

inv = get("/api/reports/inventory")
eq("Inventory · total units", sum(p["total"] for p in inv["by_project"]), one("SELECT COUNT(*) FROM units"))
eq("Inventory · available", sum(p["available"] for p in inv["by_project"]), one("SELECT COUNT(*) FROM units WHERE status='available'"))
eq("Inventory · on hold", sum(p["hold"] for p in inv["by_project"]), one("SELECT COUNT(*) FROM units WHERE status='hold'"))
eq("Inventory · booked/sold", sum(p["booked"] for p in inv["by_project"]), one("SELECT COUNT(*) FROM units WHERE status IN ('booked','sold')"))
eq("Inventory · delivered", sum(p["delivered"] for p in inv["by_project"]), one("SELECT COUNT(*) FROM units WHERE status='possession_delivered'"))
eq("Inventory · unsold value", sum(p["available_value"] for p in inv["by_project"]),
   one("SELECT COALESCE(SUM(base_sale_price),0) FROM units WHERE status='available'"))

cb = get("/api/reports/customer-balances")
eq("Customer balances · sale value = active sales", cb["totals"]["sale_value"], ov["sales_value"])
eq("Customer balances · paid", cb["totals"]["paid"],
   one("SELECT COALESCE(SUM(p.amount),0) FROM payments p JOIN bookings b ON b.id=p.booking_id WHERE b.status='active'"))
eq("Customer balances · overdue = ageing", cb["totals"]["overdue"], ag["total"])

pay = get("/api/reports/payables")
eq("Payables · vendor ordered", pay["totals"]["vendor_ordered"], one("SELECT COALESCE(SUM(total),0) FROM purchase_orders WHERE status!='cancelled'"))
eq("Payables · vendor paid (incl. advances without a PO)", pay["totals"]["vendor_paid"],
   one("SELECT COALESCE(SUM(amount),0) FROM vendor_payments"))
eq("Payables · agent balance", pay["totals"]["agent_balance"],
   one("SELECT COALESCE(SUM(MAX(commission_amount-paid_amount,0)),0) FROM agent_commissions WHERE status!='reversed'"))

bud = get("/api/reports/budget")
eq("Budget · planned", sum(line["planned_amount"] for line in bud["lines"]), one("SELECT COALESCE(SUM(planned_amount),0) FROM project_budget_lines"))

S = "4. Accounting reports"
tb = get("/api/reports/trial-balance?date_to=2999-12-31")
check(S, "Trial balance: debits = credits", tb["balanced"], f"{tb['total_debit']:,} / {tb['total_credit']:,}")
bs = get("/api/reports/balance-sheet?date_to=2999-12-31")
check(S, "Balance sheet: assets = liabilities + equity", bs["balanced"],
      f"{bs['total_assets']:,} = {bs['total_liabilities']:,} + {bs['total_equity']:,}")
acct = {a["code"]: a for a in tb["accounts"]}
bal = lambda code: (acct[code]["debit"] - acct[code]["credit"]) if code in acct else 0
cash_raw = (one("SELECT COALESCE(SUM(amount),0) FROM payments p WHERE NOT EXISTS (SELECT 1 FROM hold_token_applications h WHERE h.payment_id=p.id)")
            + one("SELECT COALESCE(SUM(amount),0) FROM hold_transactions WHERE direction='in'")
            - one("SELECT COALESCE(SUM(amount),0) FROM hold_transactions WHERE direction='refund'")
            + one("SELECT COALESCE(SUM(transfer_fee),0) FROM booking_transfers")
            - one("SELECT COALESCE(SUM(refund_amount),0) FROM booking_cancellations")
            - one("SELECT COALESCE(SUM(amount),0) FROM vendor_payments")
            - one("SELECT COALESCE(SUM(amount),0) FROM contractor_payments")
            - one("SELECT COALESCE(SUM(amount),0) FROM agent_commission_payments")
            - one("SELECT COALESCE(SUM(amount),0) FROM agent_bonuses")
            + one("SELECT COALESCE(SUM(amount),0) FROM investor_contributions")
            - one("SELECT COALESCE(SUM(amount),0) FROM investor_distributions")
            + one("SELECT COALESCE(SUM(amount),0) FROM partner_contributions")
            - one("SELECT COALESCE(SUM(amount),0) FROM partner_distributions")
            + one("SELECT COALESCE(SUM(CASE WHEN direction='in' THEN amount ELSE -amount END),0) FROM ledger_entries"))
eq("Cash + bank = all money in − all money out", bal("1010") + bal("1020"), cash_raw, S)
cb_resp = get("/api/ledger")
if isinstance(cb_resp, dict) and "rows" in cb_resp:
    rows = cb_resp["rows"]
    net = sum((x.get("inflow") or 0) - (x.get("outflow") or 0) for x in rows)
    eq("Cash + bank = Accounts page cashbook balance", bal("1010") + bal("1020"), net, S)
eq("Sales account = all bookings ever made", -bal("4000"), one("SELECT COALESCE(SUM(final_sale_price),0) FROM bookings"), S)
eq("Receivables = sale value − payments (active bookings)", bal("1100"),
   one("SELECT COALESCE(SUM(final_sale_price),0) FROM bookings WHERE status='active'")
   - one("SELECT COALESCE(SUM(p.amount),0) FROM payments p JOIN bookings b ON b.id=p.booking_id WHERE b.status='active'"), S)
eq("Vendor payables = Payables report balance", -bal("2000"), pay["totals"]["vendor_balance"], S)
eq("Commission payable = Payables report balance", -bal("2300"), pay["totals"]["agent_balance"], S)
eq("Investor funds = contributions", -bal("2500"), one("SELECT COALESCE(SUM(amount),0) FROM investor_contributions"), S)
eq("Construction materials = non-cancelled purchase orders", bal("5000"),
   one("SELECT COALESCE(SUM(total),0) FROM purchase_orders WHERE status!='cancelled'"), S)
nb = q("SELECT po_no, total FROM purchase_orders WHERE status!='cancelled' AND budget_category_id IS NULL")
check("2. Data consistency", "Every purchase order has a budget category", not nb,
      ", ".join(f"{r[0]} (PKR {r[1]:,}) is not counted in any budget" for r in nb))
mo = get("/api/reports/monthly")
eq("Monthly in & out closing = cash + bank", mo["closing"], bal("1010") + bal("1020"), S)
ex = get("/api/reports/expense-ledger")
eq("Expense ledger total = expense accounts", ex["total"], sum(bal(c) for c in acct if c.startswith("5")), S)
pw = get("/api/reports/project-wise")
eq("Project wise receivable = open installments", pw["totals"]["receivable"],
   one("""SELECT COALESCE(SUM(i.remaining_amount),0) FROM installments i JOIN bookings b ON b.id=i.booking_id
          WHERE b.status='active' AND i.status IN ('pending','partial','overdue')"""), S)
eq("Project wise overdue = ageing total", pw["totals"]["overdue"], ag["total"], S)
eq("Project wise units = inventory", pw["totals"]["units"], one("SELECT COUNT(*) FROM units"), S)
prog = {p["project_id"]: p["progress"] for p in pw["projects"]}
raw_prog = {r[0]: r[1] or 0 for r in q("SELECT id, current_progress FROM projects")}
check(S, "Project wise 'Built %' = project progress", prog == raw_prog, f"report {prog} / database {raw_prog}")

S = "5. Dashboard & Recovery vs reports"
dash = get("/api/dashboard")
k = dash.get("kpi", {})
eq("Dashboard receivable = open installments (active bookings)", k.get("receivable"), pw["totals"]["receivable"], S)
eq("Dashboard overdue list = Ageing total", sum(x["amount"] for x in dash["overdue"]), ag["total"], S)
eq("Dashboard units sold = inventory booked/sold/delivered", k.get("sold"),
   one("SELECT COUNT(*) FROM units WHERE status IN ('booked','sold','possession_delivered')"), S)
token = one("SELECT COALESCE(SUM(amount),0) FROM payments p WHERE EXISTS (SELECT 1 FROM hold_token_applications h WHERE h.payment_id=p.id)")
eq("Dashboard collected = all payments except hold tokens already counted", k.get("collected_total"),
   one("SELECT COALESCE(SUM(amount),0) FROM payments") - token, S)
eq("Dashboard payable = vendor + agent balances", k.get("payable"),
   pay["totals"]["vendor_balance"] + pay["totals"]["agent_balance"], S)
rec = get("/api/recovery")
eq("Recovery receivable = Dashboard receivable", rec["receivable"], k.get("receivable"), S)
eq("Recovery overdue = Ageing total", rec["overdue_amt"], ag["total"], S)

client.__exit__(None, None, None)
print(json.dumps(results))
