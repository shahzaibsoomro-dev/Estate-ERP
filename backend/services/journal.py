"""System-generated double-entry journal.

The ERP records business events (bookings, payments, purchase orders, commissions, ...)
rather than journal vouchers. This module turns those events into balanced journal
entries so the accounting reports (trial balance, general ledger, balance sheet,
expense ledger, monthly in/out) all come from one consistent source.

Policy: a booking is recognised as sales revenue on its booking date; the unpaid part
is a customer receivable. Purchase orders are expensed (and owed to the vendor) on
their order date; commissions when the booking is made. Everything else is cash basis.
Each entry belongs to at most one project, so a project-filtered journal still balances.
"""
from backend.database import fetch_all

# code: (name, type, group)
ACCOUNTS = {
    "1010": ("Cash in hand", "asset", "Cash & bank"),
    "1020": ("Bank accounts", "asset", "Cash & bank"),
    "1100": ("Customer receivables", "asset", "Receivables"),
    "2000": ("Vendor payables", "liability", "Payables"),
    "2100": ("Customer refunds payable", "liability", "Customer liabilities"),
    "2200": ("Hold token deposits", "liability", "Customer liabilities"),
    "2300": ("Agent commission payable", "liability", "Payables"),
    "2500": ("Investor funds", "liability", "Funding"),
    "3000": ("Partner capital", "equity", "Capital"),
    "3100": ("Partner drawings", "equity", "Capital"),
    "4000": ("Property sales", "income", "Sales"),
    "4090": ("Sales cancellations", "income", "Sales"),
    "4100": ("Transfer fee income", "income", "Other income"),
    "4200": ("Forfeiture income", "income", "Other income"),
    "4300": ("Other income", "income", "Other income"),
    "5000": ("Construction materials", "expense", "Construction cost"),
    "5100": ("Contractor costs", "expense", "Construction cost"),
    "5200": ("Agent commissions", "expense", "Selling cost"),
    "5210": ("Agent bonuses", "expense", "Selling cost"),
    "5300": ("Investor returns", "expense", "Finance cost"),
    "5800": ("Cancellation losses", "expense", "Other expenses"),
    "5900": ("Other expenses", "expense", "Other expenses"),
}
TYPE_ORDER = ["asset", "liability", "equity", "income", "expense"]
DEBIT_NORMAL = {"asset", "expense"}
CASH_ACCOUNTS = ("1010", "1020")

# Cash-flow labels for the monthly in & out report, keyed by entry source.
SOURCE_LABEL = {
    "payment": "Customer collections", "hold_in": "Hold tokens", "hold_refund": "Hold token refunds",
    "transfer": "Transfer fees", "cancel_refund": "Cancellation refunds", "vendor_payment": "Vendor payments",
    "po_cancel_fee": "PO cancellation fees", "po_cancel_refund": "PO cancellation refunds",
    "contractor_payment": "Contractor payments", "commission_payment": "Agent commissions",
    "agent_bonus": "Agent bonuses", "investor_in": "Investor funding", "investor_out": "Investor returns",
    "partner_in": "Partner capital", "partner_out": "Partner drawings", "manual": "Cashbook entries",
}


def cash_account(method: str | None) -> str:
    return "1010" if (method or "").strip().lower() == "cash" else "1020"


def _e(entries, date, source, ref, narration, project_id, party, lines):
    lines = [(a, int(d or 0), int(c or 0)) for a, d, c in lines if (d or c)]
    if lines and date:
        entries.append({"date": str(date)[:10], "source": source, "ref": ref, "narration": narration,
                        "project_id": project_id, "party": party, "lines": lines})


def _safe(conn, sql):
    try:
        return fetch_all(conn, sql)
    except Exception:  # optional tables on older databases
        return []


def build(conn, project_ids: list[int] | None = None, end: str | None = None) -> list[dict]:
    """All journal entries (optionally up to `end` and limited to projects), sorted by date."""
    E: list[dict] = []

    for b in fetch_all(conn, """SELECT b.id, b.booking_no, b.booking_date, b.final_sale_price, b.project_id,
                                       c.name AS customer, u.unit_no
                                FROM bookings b JOIN customers c ON c.id=b.customer_id
                                LEFT JOIN units u ON u.id=b.unit_id"""):
        _e(E, b["booking_date"], "booking", b["booking_no"], f"Sale · {b['unit_no'] or ''} · {b['customer']}",
           b["project_id"], b["customer"], [("1100", b["final_sale_price"], 0), ("4000", 0, b["final_sale_price"])])

    token_paid = {r["payment_id"] for r in _safe(conn, "SELECT payment_id FROM hold_token_applications")}
    for p in fetch_all(conn, """SELECT p.id, p.amount, p.payment_date, p.payment_method, p.booking_id,
                                       b.booking_no, b.project_id, c.name AS customer, r.receipt_no
                                FROM payments p JOIN customers c ON c.id=p.customer_id
                                LEFT JOIN bookings b ON b.id=p.booking_id
                                LEFT JOIN receipts r ON r.payment_id=p.id"""):
        credit = "1100" if p["booking_id"] else "2100"
        if p["id"] in token_paid:
            _e(E, p["payment_date"], "token_applied", p["receipt_no"] or p["booking_no"],
               f"Hold token applied · {p['customer']}", p["project_id"], p["customer"],
               [("2200", p["amount"], 0), (credit, 0, p["amount"])])
        else:
            _e(E, p["payment_date"], "payment", p["receipt_no"] or p["booking_no"],
               f"Collection · {p['customer']} · {p['booking_no'] or ''}", p["project_id"], p["customer"],
               [(cash_account(p["payment_method"]), p["amount"], 0), (credit, 0, p["amount"])])

    paid_by_booking = {r["booking_id"]: r["paid"] for r in fetch_all(
        conn, "SELECT booking_id, SUM(amount) AS paid FROM payments WHERE booking_id IS NOT NULL GROUP BY booking_id")}
    for x in fetch_all(conn, """SELECT bc.id, bc.cancelled_at, bc.refund_amount, b.id AS booking_id, b.booking_no,
                                       b.final_sale_price, b.project_id, c.name AS customer
                                FROM booking_cancellations bc JOIN bookings b ON b.id=bc.booking_id
                                JOIN customers c ON c.id=b.customer_id"""):
        price = x["final_sale_price"] or 0
        paid = paid_by_booking.get(x["booking_id"], 0) or 0
        refund = x["refund_amount"] or 0
        retained = paid - refund
        lines = [("4090", price, 0), ("1100", 0, price - paid), ("2100", 0, paid)]
        if refund:
            lines += [("2100", refund, 0), ("1020", 0, refund)]
        if retained > 0:
            lines += [("2100", retained, 0), ("4200", 0, retained)]
        elif retained < 0:
            lines += [("5800", -retained, 0), ("2100", 0, -retained)]
        _e(E, x["cancelled_at"], "cancellation", x["booking_no"], f"Cancellation · {x['customer']} · {x['booking_no']}",
           x["project_id"], x["customer"], lines)
        if refund and E and E[-1]["ref"] == x["booking_no"]:
            E[-1]["source"] = "cancel_refund"

    for h in _safe(conn, """SELECT ht.id, ht.direction, ht.amount, ht.txn_date, ht.payment_method, ht.voucher_no,
                                   u.project_id, u.unit_no, COALESCE(c.name,'Customer') AS customer, hr.receipt_no
                            FROM hold_transactions ht JOIN unit_holds h ON h.id=ht.hold_id
                            JOIN units u ON u.id=h.unit_id LEFT JOIN customers c ON c.id=h.customer_id
                            LEFT JOIN hold_receipts hr ON hr.transaction_id=ht.id
                            WHERE ht.amount > 0"""):
        cash = cash_account(h["payment_method"])
        if h["direction"] == "in":
            _e(E, h["txn_date"], "hold_in", h["receipt_no"], f"Hold token · {h['customer']} · {h['unit_no']}",
               h["project_id"], h["customer"], [(cash, h["amount"], 0), ("2200", 0, h["amount"])])
        elif h["direction"] == "refund":
            _e(E, h["txn_date"], "hold_refund", h["voucher_no"], f"Hold refund · {h['customer']} · {h['unit_no']}",
               h["project_id"], h["customer"], [("2200", h["amount"], 0), (cash, 0, h["amount"])])

    for t in _safe(conn, """SELECT bt.id, bt.transfer_date, bt.transfer_fee, b.project_id, b.booking_no, c.name AS customer
                            FROM booking_transfers bt JOIN bookings b ON b.id=bt.booking_id
                            JOIN customers c ON c.id=bt.to_customer_id WHERE COALESCE(bt.transfer_fee,0) > 0"""):
        _e(E, t["transfer_date"], "transfer", t["booking_no"], f"Transfer fee · {t['booking_no']} · {t['customer']}",
           t["project_id"], t["customer"], [("1020", t["transfer_fee"], 0), ("4100", 0, t["transfer_fee"])])

    for po in fetch_all(conn, """SELECT po.id, po.po_no, po.order_date, po.total, po.project_id, po.material,
                                        COALESCE(bc.name, po.category, 'Materials') AS category, v.name AS vendor
                                 FROM purchase_orders po JOIN vendors v ON v.id=po.vendor_id
                                 LEFT JOIN budget_categories bc ON bc.id=po.budget_category_id
                                 WHERE po.status != 'cancelled'"""):
        e_start = len(E)
        _e(E, po["order_date"], "purchase", po["po_no"], f"{po['category']} · {po['material'] or ''} · {po['vendor']}",
           po["project_id"], po["vendor"], [("5000", po["total"], 0), ("2000", 0, po["total"])])
        if len(E) > e_start:
            E[-1]["category"] = po["category"]
    for po in _safe(conn, """SELECT po.id, po.po_no, COALESCE(po.cancelled_at, po.order_date) AS cancelled_at,
                                    COALESCE(po.cancel_fee_amount,0) AS fee, po.project_id, v.name AS vendor
                             FROM purchase_orders po JOIN vendors v ON v.id=po.vendor_id
                             WHERE po.status='cancelled' AND COALESCE(po.cancel_fee_amount,0) > 0"""):
        _e(E, po["cancelled_at"], "po_cancel_fee", po["po_no"],
           f"PO cancel fee · {po['po_no']} · {po['vendor']}", po["project_id"], po["vendor"],
           [("5800", po["fee"], 0), ("2000", 0, po["fee"])])
    for vp in fetch_all(conn, """SELECT vp.id, vp.amount, vp.payment_date, vp.payment_method, vp.reference_number,
                                        v.name AS vendor, po.po_no, po.project_id
                                 FROM vendor_payments vp JOIN vendors v ON v.id=vp.vendor_id
                                 LEFT JOIN purchase_orders po ON po.id=vp.purchase_order_id"""):
        cash = cash_account(vp["payment_method"])
        amt = int(vp["amount"] or 0)
        if amt < 0:
            amt = -amt
            _e(E, vp["payment_date"], "po_cancel_refund", vp["reference_number"] or vp["po_no"],
               f"PO cancel refund · {vp['vendor']} · {vp['po_no'] or ''}", vp["project_id"], vp["vendor"],
               [(cash, amt, 0), ("2000", 0, amt)])
        elif amt > 0:
            _e(E, vp["payment_date"], "vendor_payment", vp["reference_number"] or vp["po_no"],
               f"Paid vendor · {vp['vendor']} · {vp['po_no'] or ''}", vp["project_id"], vp["vendor"],
               [("2000", amt, 0), (cash, 0, amt)])

    for cp in _safe(conn, """SELECT cp.id, cp.amount, cp.payment_date, cp.payment_method, cp.reference_number,
                                    cp.project_id, c.name AS contractor
                             FROM contractor_payments cp JOIN contractors c ON c.id=cp.contractor_id"""):
        _e(E, cp["payment_date"], "contractor_payment", cp["reference_number"], f"Contractor · {cp['contractor']}",
           cp["project_id"], cp["contractor"],
           [("5100", cp["amount"], 0), (cash_account(cp["payment_method"]), 0, cp["amount"])])

    for ac in _safe(conn, """SELECT ac.id, ac.commission_amount, b.booking_date, b.booking_no, b.project_id, a.name AS agent
                             FROM agent_commissions ac JOIN bookings b ON b.id=ac.booking_id
                             JOIN agents a ON a.id=ac.agent_id WHERE ac.status != 'reversed'"""):
        _e(E, ac["booking_date"], "commission", ac["booking_no"], f"Commission earned · {ac['agent']} · {ac['booking_no']}",
           ac["project_id"], ac["agent"], [("5200", ac["commission_amount"], 0), ("2300", 0, ac["commission_amount"])])
    for pay in _safe(conn, """SELECT acp.id, acp.amount, acp.payment_date, b.booking_no, b.project_id, a.name AS agent
                              FROM agent_commission_payments acp JOIN agent_commissions ac ON ac.id=acp.commission_id
                              JOIN agents a ON a.id=ac.agent_id LEFT JOIN bookings b ON b.id=ac.booking_id"""):
        _e(E, pay["payment_date"], "commission_payment", pay["booking_no"], f"Paid commission · {pay['agent']}",
           pay["project_id"], pay["agent"], [("2300", pay["amount"], 0), ("1020", 0, pay["amount"])])
    for bo in _safe(conn, """SELECT ab.id, ab.amount, ab.bonus_date, ab.reason, a.name AS agent
                             FROM agent_bonuses ab JOIN agents a ON a.id=ab.agent_id"""):
        _e(E, bo["bonus_date"], "agent_bonus", None, f"Agent bonus · {bo['agent']} · {bo['reason'] or ''}",
           None, bo["agent"], [("5210", bo["amount"], 0), ("1020", 0, bo["amount"])])

    for kind, capital, payout, name_tbl in (("investor", "2500", "5300", "investors"), ("partner", "3000", "3100", "partners")):
        fk = f"{kind}_id"
        for r in _safe(conn, f"""SELECT x.id, x.amount, x.contribution_date AS d, a.project_id, n.name
                                 FROM {kind}_contributions x JOIN {kind}_agreements a ON a.id=x.agreement_id
                                 JOIN {name_tbl} n ON n.id=a.{fk}"""):
            _e(E, r["d"], f"{kind}_in", None, f"{kind.title()} funding · {r['name']}", r["project_id"], r["name"],
               [("1020", r["amount"], 0), (capital, 0, r["amount"])])
        for r in _safe(conn, f"""SELECT x.id, x.amount, x.distribution_date AS d, a.project_id, n.name
                                 FROM {kind}_distributions x JOIN {kind}_agreements a ON a.id=x.agreement_id
                                 JOIN {name_tbl} n ON n.id=a.{fk}"""):
            label = "return" if kind == "investor" else "drawing"
            _e(E, r["d"], f"{kind}_out", None, f"{kind.title()} {label} · {r['name']}", r["project_id"], r["name"],
               [(payout, r["amount"], 0), ("1020", 0, r["amount"])])

    cols = {r[1] for r in conn.execute("PRAGMA table_info(ledger_entries)")}
    extra = ", payment_method, project_id" if {"payment_method", "project_id"} <= cols else ", NULL AS payment_method, NULL AS project_id"
    for m in fetch_all(conn, f"SELECT id, entry_date, narration, amount, direction, category{extra} FROM ledger_entries"):
        amt = m["amount"] or 0
        cash = cash_account(m["payment_method"])
        if m["direction"] == "in":
            lines = [(cash, amt, 0), ("4300", 0, amt)]
        else:
            lines = [("5900", amt, 0), (cash, 0, amt)]
        before = len(E)
        _e(E, m["entry_date"], "manual", f"CB-{m['id']}", m["narration"], m["project_id"], None, lines)
        if len(E) > before:
            E[-1]["category"] = m["category"] or ("Other income" if m["direction"] == "in" else "Other expenses")

    if project_ids is not None:
        allowed = set(project_ids)
        E = [e for e in E if e["project_id"] in allowed]
    if end:
        E = [e for e in E if e["date"] <= end]
    E.sort(key=lambda e: (e["date"], e["source"], str(e["ref"] or "")))
    return E


def account_info(code: str) -> dict:
    name, typ, group = ACCOUNTS[code]
    return {"code": code, "name": name, "type": typ, "group": group}


def signed(code: str, debit: int, credit: int) -> int:
    """Balance in the account's normal direction."""
    return (debit - credit) if ACCOUNTS[code][1] in DEBIT_NORMAL else (credit - debit)


def totals(entries, start: str | None = None, end: str | None = None) -> dict[str, list[int]]:
    """{code: [debit, credit]} for entries in [start, end]."""
    out: dict[str, list[int]] = {}
    for e in entries:
        if (start and e["date"] < start) or (end and e["date"] > end):
            continue
        for a, d, c in e["lines"]:
            t = out.setdefault(a, [0, 0])
            t[0] += d
            t[1] += c
    return out
