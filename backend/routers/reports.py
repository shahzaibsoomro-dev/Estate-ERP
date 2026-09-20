"""Management reports. All accept optional `project_ids` (comma list); period reports accept
`date_from` / `date_to` (YYYY-MM-DD). Company-wide by nature, so employees need all-project access."""
import json
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query

from backend.database import fetch_all, fetch_one, get_db
from backend.services import budget as budget_svc
from backend.services import installments as inst_svc
from backend.services import journal
from backend.services.project_filter import parse_project_ids, sql_in
from backend.services.units import normalize_unit_type, type_label


def _unit_type_label(raw):
    try:
        return type_label(normalize_unit_type(raw))
    except (ValueError, AttributeError, TypeError):
        return raw or "Other"

router = APIRouter(prefix="/api/reports", tags=["reports"])

OPEN_STATUSES = "('pending','partial','overdue')"


def _period(date_from: str | None, date_to: str | None) -> tuple[str, str]:
    try:
        start = date.fromisoformat(date_from) if date_from else date(1900, 1, 1)
        end = date.fromisoformat(date_to) if date_to else date(2999, 12, 31)
    except ValueError as e:
        raise HTTPException(400, "Dates must be YYYY-MM-DD") from e
    if start > end:
        raise HTTPException(400, "Start date is after end date")
    return start.isoformat(), end.isoformat()


def _ids(project_ids: str | None) -> list[int] | None:
    try:
        return parse_project_ids(project_ids)
    except ValueError as e:
        raise HTTPException(400, "Invalid project filter") from e


def _bucket(days: int) -> str:
    if days <= 30:
        return "1–30 days"
    if days <= 60:
        return "31–60 days"
    if days <= 90:
        return "61–90 days"
    return "90+ days"


BUCKETS = ["1–30 days", "31–60 days", "61–90 days", "90+ days"]


# ---------------------------------------------------------------- overview
@router.get("/overview")
def overview(project_ids: str | None = Query(None), date_from: str | None = None, date_to: str | None = None):
    ids = _ids(project_ids)
    start, end = _period(date_from, date_to)
    pf_b, pp_b = sql_in("b.project_id", ids)
    pf_u, pp_u = sql_in("u.project_id", ids)
    with get_db() as conn:
        inst_svc.refresh_statuses(conn)
        sales = fetch_one(conn, f"""SELECT COUNT(*) n, COALESCE(SUM(b.final_sale_price),0) v FROM bookings b
                                    WHERE b.status='active' AND b.booking_date BETWEEN ? AND ?{pf_b}""", (start, end, *pp_b))
        coll = fetch_one(conn, f"""SELECT COUNT(*) n, COALESCE(SUM(p.amount),0) v FROM payments p
                                   JOIN bookings b ON b.id=p.booking_id
                                   WHERE p.payment_date BETWEEN ? AND ?{pf_b}""", (start, end, *pp_b))
        recv = fetch_one(conn, f"""SELECT COALESCE(SUM(i.remaining_amount),0) v FROM installments i JOIN units u ON u.id=i.unit_id
                                   JOIN bookings bk ON bk.id=i.booking_id AND bk.status='active'
                                   WHERE i.status IN {OPEN_STATUSES}{pf_u}""", pp_u)
        overdue = fetch_one(conn, f"""SELECT COUNT(*) n, COALESCE(SUM(i.remaining_amount),0) v FROM installments i
                                      JOIN units u ON u.id=i.unit_id
                                      JOIN bookings bk ON bk.id=i.booking_id AND bk.status='active'
                                      WHERE i.status IN ('overdue','partial') AND i.remaining_amount>0
                                        AND i.due_date < date('now'){pf_u}""", pp_u)
        avail = fetch_one(conn, f"""SELECT COUNT(*) n, COALESCE(SUM(u.base_sale_price),0) v FROM units u
                                    WHERE u.status='available'{pf_u}""", pp_u)
        cancelled = fetch_one(conn, f"""SELECT COUNT(*) n FROM bookings b WHERE b.status='cancelled'
                                        AND b.booking_date BETWEEN ? AND ?{pf_b}""", (start, end, *pp_b))
    return {
        "bookings": sales["n"], "sales_value": sales["v"],
        "collections": coll["v"], "collection_count": coll["n"],
        "receivable": recv["v"], "overdue": overdue["v"], "overdue_count": overdue["n"],
        "available_units": avail["n"], "available_value": avail["v"],
        "cancelled_bookings": cancelled["n"],
    }


# ---------------------------------------------------------------- receivables ageing
@router.get("/ageing")
def ageing(project_ids: str | None = Query(None)):
    ids = _ids(project_ids)
    pf, pp = sql_in("u.project_id", ids)
    with get_db() as conn:
        inst_svc.refresh_statuses(conn)
        items = fetch_all(
            conn,
            f"""SELECT i.id, i.booking_id, i.customer_id, i.due_date, i.remaining_amount AS amount,
                       i.status, i.type, i.installment_no,
                       c.name AS customer_name, c.contact_number AS phone, u.unit_no,
                       p.id AS project_id, p.name AS project_name, b.booking_no,
                       CAST(julianday('now') - julianday(i.due_date) AS INTEGER) AS days_overdue
                FROM installments i
                JOIN customers c ON c.id=i.customer_id
                JOIN units u ON u.id=i.unit_id
                JOIN projects p ON p.id=u.project_id
                JOIN bookings b ON b.id=i.booking_id AND b.status='active'
                WHERE i.status IN ('overdue','partial') AND i.remaining_amount > 0
                  AND i.due_date < date('now'){pf}
                ORDER BY days_overdue DESC, c.name""",
            pp,
        )
    d30 = d60 = d90 = 0
    buckets = {b: {"bucket": b, "amount": 0, "count": 0} for b in BUCKETS}
    by_project: dict[int, dict] = {}
    by_customer: dict[int, dict] = {}
    for r in items:
        days = r.get("days_overdue") or 0
        amt = r.get("amount") or 0
        r["bucket"] = _bucket(days)
        # legacy fields kept for existing callers
        if days <= 30:
            d30 += amt
        elif days <= 60:
            d60 += amt
        else:
            d90 += amt
        buckets[r["bucket"]]["amount"] += amt
        buckets[r["bucket"]]["count"] += 1
        p = by_project.setdefault(r["project_id"], {"project_id": r["project_id"], "project_name": r["project_name"], "amount": 0, "count": 0,
                                                     **{b: 0 for b in BUCKETS}})
        p["amount"] += amt
        p["count"] += 1
        p[r["bucket"]] += amt
        cust = by_customer.setdefault(r["customer_id"], {
            "customer_id": r["customer_id"], "customer_name": r["customer_name"], "phone": r["phone"],
            "amount": 0, "count": 0, "oldest_days": 0, "units": set()})
        cust["amount"] += amt
        cust["count"] += 1
        cust["oldest_days"] = max(cust["oldest_days"], days)
        cust["units"].add(r["unit_no"])
    customers = sorted(by_customer.values(), key=lambda c: -c["amount"])
    for c in customers:
        c["units"] = ", ".join(sorted(c["units"]))
    return {
        "d30": d30, "d60": d60, "d90": d90, "items": items,
        "total": sum(b["amount"] for b in buckets.values()),
        "buckets": list(buckets.values()),
        "by_project": sorted(by_project.values(), key=lambda x: -x["amount"]),
        "by_customer": customers,
    }


# ---------------------------------------------------------------- sales
@router.get("/sales")
def sales_legacy():
    """Kept for existing callers: active bookings per project (all time)."""
    with get_db() as conn:
        return fetch_all(
            conn,
            """SELECT p.name AS project_name, COUNT(b.id) AS bookings,
                      COALESCE(SUM(b.final_sale_price),0) AS total_sales,
                      COALESCE(SUM(b.booking_amount),0) AS collected_dp
               FROM bookings b JOIN projects p ON p.id=b.project_id
               WHERE b.status='active' GROUP BY b.project_id""",
        )


@router.get("/sales-summary")
def sales_summary(project_ids: str | None = Query(None), date_from: str | None = None, date_to: str | None = None):
    ids = _ids(project_ids)
    start, end = _period(date_from, date_to)
    pf, pp = sql_in("b.project_id", ids)
    with get_db() as conn:
        by_project = fetch_all(
            conn,
            f"""SELECT p.id AS project_id, p.name AS project_name,
                       COUNT(b.id) AS bookings,
                       COALESCE(SUM(b.final_sale_price),0) AS sales_value,
                       COALESCE(SUM(b.booking_amount),0) AS booking_amounts,
                       COALESCE(AVG(b.final_sale_price),0) AS avg_price,
                       COALESCE(SUM(b.base_sale_price - b.final_sale_price),0) AS discounts,
                       SUM(CASE WHEN b.agent_id IS NOT NULL THEN 1 ELSE 0 END) AS via_agent
                FROM bookings b JOIN projects p ON p.id=b.project_id
                WHERE b.status='active' AND b.booking_date BETWEEN ? AND ?{pf}
                GROUP BY p.id ORDER BY sales_value DESC""",
            (start, end, *pp),
        )
        for row in by_project:
            paid = fetch_one(conn, """SELECT COALESCE(SUM(py.amount),0) v FROM payments py JOIN bookings b ON b.id=py.booking_id
                                      WHERE b.project_id=? AND b.status='active' AND b.booking_date BETWEEN ? AND ?""",
                             (row["project_id"], start, end))["v"]
            row["collected"] = paid
            row["outstanding"] = max(row["sales_value"] - paid, 0)
            row["collected_pct"] = round(paid / row["sales_value"] * 100) if row["sales_value"] else 0
            row["avg_price"] = round(row["avg_price"])
        monthly = fetch_all(
            conn,
            f"""SELECT strftime('%Y-%m', b.booking_date) AS month, COUNT(*) AS bookings,
                       COALESCE(SUM(b.final_sale_price),0) AS sales_value
                FROM bookings b WHERE b.status='active' AND b.booking_date BETWEEN ? AND ?{pf}
                GROUP BY month ORDER BY month""",
            (start, end, *pp),
        )
        by_type = fetch_all(
            conn,
            f"""SELECT COALESCE(u.unit_type,'Other') AS unit_type, COUNT(*) AS bookings,
                       COALESCE(SUM(b.final_sale_price),0) AS sales_value
                FROM bookings b JOIN units u ON u.id=b.unit_id
                WHERE b.status='active' AND b.booking_date BETWEEN ? AND ?{pf}
                GROUP BY unit_type ORDER BY sales_value DESC""",
            (start, end, *pp),
        )
        bookings = fetch_all(
            conn,
            f"""SELECT b.id, b.booking_no, b.booking_date, b.final_sale_price, b.booking_amount, b.project_id,
                       c.name AS customer_name, u.unit_no, u.unit_type, p.name AS project_name,
                       COALESCE(a.name,'Direct') AS agent_name
                FROM bookings b JOIN customers c ON c.id=b.customer_id JOIN units u ON u.id=b.unit_id
                JOIN projects p ON p.id=b.project_id LEFT JOIN agents a ON a.id=b.agent_id
                WHERE b.status='active' AND b.booking_date BETWEEN ? AND ?{pf}
                ORDER BY b.booking_date DESC""",
            (start, end, *pp),
        )
        cancelled = fetch_one(conn, f"""SELECT COUNT(*) n FROM bookings b WHERE b.status='cancelled'
                                        AND b.booking_date BETWEEN ? AND ?{pf}""", (start, end, *pp))["n"]
        for row in by_type:
            row["unit_type"] = _unit_type_label(row.get("unit_type"))
        for row in bookings:
            row["unit_type"] = _unit_type_label(row.get("unit_type"))
    return {"by_project": by_project, "monthly": monthly, "by_type": by_type, "bookings": bookings,
            "cancelled": cancelled}


# ---------------------------------------------------------------- collections
@router.get("/collections")
def collections(project_ids: str | None = Query(None), date_from: str | None = None, date_to: str | None = None):
    ids = _ids(project_ids)
    start, end = _period(date_from, date_to)
    pf, pp = sql_in("b.project_id", ids)
    base = f"""FROM payments py JOIN bookings b ON b.id=py.booking_id
               JOIN projects p ON p.id=b.project_id
               WHERE py.payment_date BETWEEN ? AND ?{pf}"""
    params = (start, end, *pp)
    with get_db() as conn:
        monthly = fetch_all(conn, f"""SELECT strftime('%Y-%m', py.payment_date) AS month, COUNT(*) AS count,
                                             SUM(py.amount) AS amount {base} GROUP BY month ORDER BY month""", params)
        by_method = fetch_all(conn, f"""SELECT COALESCE(py.payment_method,'Other') AS method, COUNT(*) AS count,
                                               SUM(py.amount) AS amount {base} GROUP BY method ORDER BY amount DESC""", params)
        by_project = fetch_all(conn, f"""SELECT p.name AS project_name, COUNT(*) AS count, SUM(py.amount) AS amount
                                         {base} GROUP BY p.id ORDER BY amount DESC""", params)
        rows = fetch_all(conn, f"""SELECT py.id, py.payment_date, py.amount, py.payment_method, py.reference_number,
                                          py.booking_id, b.project_id, r.receipt_no, c.name AS customer_name,
                                          u.unit_no, p.name AS project_name, COALESCE(i.type,'General') AS against
                                   FROM payments py JOIN bookings b ON b.id=py.booking_id
                                   JOIN projects p ON p.id=b.project_id
                                   JOIN customers c ON c.id=py.customer_id
                                   JOIN units u ON u.id=b.unit_id
                                   LEFT JOIN receipts r ON r.payment_id=py.id
                                   LEFT JOIN installments i ON i.id=py.installment_id
                                   WHERE py.payment_date BETWEEN ? AND ?{pf}
                                   ORDER BY py.payment_date DESC, py.id DESC""", params)
        due = fetch_one(conn, f"""SELECT COALESCE(SUM(i.amount),0) v FROM installments i JOIN bookings b ON b.id=i.booking_id
                                  WHERE i.status!='cancelled' AND i.due_date BETWEEN ? AND ?
                                    AND i.due_date <= date('now'){pf}""", params)["v"]
    total = sum(r["amount"] for r in rows)
    return {"total": total, "count": len(rows), "due_in_period": due,
            "collection_rate": round(total / due * 100) if due else None,
            "monthly": monthly, "by_method": by_method, "by_project": by_project, "payments": rows}


# ---------------------------------------------------------------- inventory
@router.get("/inventory")
def inventory(project_ids: str | None = Query(None)):
    ids = _ids(project_ids)
    pf, pp = sql_in("p.id", ids)
    with get_db() as conn:
        rows = fetch_all(
            conn,
            f"""SELECT p.id AS project_id, p.name AS project_name, p.status AS project_status,
                       p.current_progress AS progress,
                       COUNT(u.id) AS total,
                       SUM(CASE WHEN u.status='available' THEN 1 ELSE 0 END) AS available,
                       SUM(CASE WHEN u.status='hold' THEN 1 ELSE 0 END) AS hold,
                       SUM(CASE WHEN u.status IN ('booked','sold') THEN 1 ELSE 0 END) AS booked,
                       SUM(CASE WHEN u.status='possession_delivered' THEN 1 ELSE 0 END) AS delivered,
                       COALESCE(SUM(CASE WHEN u.status='available' THEN u.base_sale_price END),0) AS available_value,
                       COALESCE(SUM(CASE WHEN u.status='hold' THEN u.base_sale_price END),0) AS hold_value
                FROM projects p LEFT JOIN units u ON u.project_id=p.id
                WHERE 1=1{pf}
                GROUP BY p.id HAVING total > 0 ORDER BY p.name""",
            pp,
        )
        for r in rows:
            r["sold_pct"] = round((r["booked"] + r["delivered"]) / r["total"] * 100) if r["total"] else 0
        pf_u, pp_u = sql_in("u.project_id", ids)
        by_type = fetch_all(
            conn,
            f"""SELECT COALESCE(u.unit_type,'Other') AS unit_type, COUNT(*) AS total,
                       SUM(CASE WHEN u.status='available' THEN 1 ELSE 0 END) AS available,
                       COALESCE(MIN(CASE WHEN u.status='available' THEN u.base_sale_price END),0) AS min_price,
                       COALESCE(MAX(CASE WHEN u.status='available' THEN u.base_sale_price END),0) AS max_price
                FROM units u WHERE 1=1{pf_u} GROUP BY unit_type ORDER BY total DESC""",
            pp_u,
        )
        for row in by_type:
            row["unit_type"] = _unit_type_label(row.get("unit_type"))
        holds = fetch_all(
            conn,
            f"""SELECT h.id, u.unit_no, u.project_id, p.name AS project_name, c.name AS customer_name,
                       h.hold_until, h.token_amount,
                       CAST(julianday(h.hold_until) - julianday('now') AS INTEGER) AS days_left
                FROM unit_holds h JOIN units u ON u.id=h.unit_id JOIN projects p ON p.id=u.project_id
                LEFT JOIN customers c ON c.id=h.customer_id
                WHERE h.status='active'{pf_u} ORDER BY h.hold_until""",
            pp_u,
        )
    return {"by_project": rows, "by_type": by_type, "holds": holds}


# ---------------------------------------------------------------- customer balances
@router.get("/customer-balances")
def customer_balances(project_ids: str | None = Query(None)):
    ids = _ids(project_ids)
    pf, pp = sql_in("b.project_id", ids)
    with get_db() as conn:
        inst_svc.refresh_statuses(conn)
        rows = fetch_all(
            conn,
            f"""SELECT c.id AS customer_id, c.name AS customer_name, c.cnic, c.contact_number AS phone,
                       COUNT(DISTINCT b.id) AS bookings,
                       GROUP_CONCAT(DISTINCT u.unit_no) AS units
                FROM customers c JOIN bookings b ON b.customer_id=c.id AND b.status='active'
                JOIN units u ON u.id=b.unit_id
                WHERE 1=1{pf}
                GROUP BY c.id""",
            pp,
        )
        for r in rows:
            agg = fetch_one(
                conn,
                f"""SELECT COALESCE(SUM(b.final_sale_price),0) sale,
                           (SELECT COALESCE(SUM(py.amount),0) FROM payments py JOIN bookings bb ON bb.id=py.booking_id
                             WHERE bb.customer_id=? AND bb.status='active'{pf.replace('b.', 'bb.')}) paid,
                           (SELECT COALESCE(SUM(i.remaining_amount),0) FROM installments i JOIN bookings bb ON bb.id=i.booking_id
                             WHERE bb.customer_id=? AND bb.status='active' AND i.status IN ('overdue','partial')
                               AND i.due_date < date('now'){pf.replace('b.', 'bb.')}) overdue,
                           (SELECT MAX(py.payment_date) FROM payments py WHERE py.customer_id=?) last_payment
                    FROM bookings b WHERE b.customer_id=? AND b.status='active'{pf}""",
                (r["customer_id"], *pp, r["customer_id"], *pp, r["customer_id"], r["customer_id"], *pp),
            )
            r.update(sale_value=agg["sale"], paid=agg["paid"], overdue=agg["overdue"], last_payment=agg["last_payment"],
                     outstanding=max(agg["sale"] - agg["paid"], 0))
            r["paid_pct"] = round(agg["paid"] / agg["sale"] * 100) if agg["sale"] else 0
            r["status"] = "Overdue" if r["overdue"] > 0 else ("Cleared" if r["outstanding"] == 0 else "On track")
    rows.sort(key=lambda x: (-x["overdue"], -x["outstanding"]))
    return {"customers": rows,
            "totals": {k: sum(r[k] for r in rows) for k in ("sale_value", "paid", "outstanding", "overdue")}}


# ---------------------------------------------------------------- payables
@router.get("/payables")
def payables(project_ids: str | None = Query(None)):
    ids = _ids(project_ids)
    pf, pp = sql_in("po.project_id", ids)
    with get_db() as conn:
        vendors = fetch_all(
            conn,
            f"""SELECT v.id AS vendor_id, v.name AS vendor_name, v.category, v.contact,
                       COUNT(po.id) AS orders, COALESCE(SUM(po.total),0) AS ordered,
                       COALESCE(SUM((SELECT COALESCE(SUM(vp.amount),0) FROM vendor_payments vp
                                     WHERE vp.purchase_order_id=po.id)),0) AS paid,
                       MAX(po.order_date) AS last_order
                FROM vendors v JOIN purchase_orders po ON po.vendor_id=v.id AND po.status!='cancelled'
                WHERE 1=1{pf}
                GROUP BY v.id""",
            pp,
        )
        # Payments not tied to a live purchase order (advances) still reduce what we owe.
        unlinked = {} if ids else {r["vendor_id"]: r["amt"] for r in fetch_all(
            conn, """SELECT vp.vendor_id, SUM(vp.amount) AS amt FROM vendor_payments vp
                     LEFT JOIN purchase_orders po ON po.id=vp.purchase_order_id
                     WHERE po.id IS NULL OR po.status='cancelled' GROUP BY vp.vendor_id""")}
        for v in vendors:
            v["advance"] = unlinked.get(v["vendor_id"], 0)
            v["paid"] += v["advance"]
            v["balance"] = v["ordered"] - v["paid"]
        agents = fetch_all(
            conn,
            """SELECT a.id AS agent_id, a.name AS agent_name, COUNT(ac.id) AS deals,
                      COALESCE(SUM(ac.commission_amount),0) AS earned, COALESCE(SUM(ac.paid_amount),0) AS paid
               FROM agents a JOIN agent_commissions ac ON ac.agent_id=a.id AND ac.status!='reversed'
               GROUP BY a.id""",
        ) if not ids else fetch_all(
            conn,
            f"""SELECT a.id AS agent_id, a.name AS agent_name, COUNT(ac.id) AS deals,
                       COALESCE(SUM(ac.commission_amount),0) AS earned, COALESCE(SUM(ac.paid_amount),0) AS paid
                FROM agents a JOIN agent_commissions ac ON ac.agent_id=a.id AND ac.status!='reversed'
                JOIN bookings b ON b.id=ac.booking_id
                WHERE 1=1{sql_in('b.project_id', ids)[0]}
                GROUP BY a.id""",
            sql_in("b.project_id", ids)[1],
        )
        for a in agents:
            a["balance"] = max(a["earned"] - a["paid"], 0)
    vendors.sort(key=lambda x: -x["balance"])
    agents.sort(key=lambda x: -x["balance"])
    return {
        "vendors": vendors, "agents": agents,
        "totals": {"vendor_balance": sum(v["balance"] for v in vendors),
                   "agent_balance": sum(a["balance"] for a in agents),
                   "vendor_ordered": sum(v["ordered"] for v in vendors),
                   "vendor_paid": sum(v["paid"] for v in vendors)},
    }


# ---------------------------------------------------------------- budget
@router.get("/budget")
def budget(project_ids: str | None = Query(None)):
    ids = _ids(project_ids)
    with get_db() as conn:
        rows = budget_svc.summary(conn)
    if ids:
        rows = [r for r in rows if r["project_id"] in ids]
    by_project: dict[int, dict] = {}
    for r in rows:
        p = by_project.setdefault(r["project_id"], {"project_name": r["project_name"], "planned": 0, "spent": 0})
        p["planned"] += r["planned_amount"]
        p["spent"] += r["actual_spent"]
    for p in by_project.values():
        p["variance"] = p["planned"] - p["spent"]
        p["pct_used"] = round(p["spent"] / p["planned"] * 100) if p["planned"] else 0
    return {"lines": rows, "by_project": sorted(by_project.values(), key=lambda x: -x["pct_used"])}


# ================================================================ accounting (system-generated journal)
def _journal(conn, ids, end=None):
    return journal.build(conn, ids, end)


def _project_names(conn) -> dict[int, str]:
    return {r["id"]: r["name"] for r in fetch_all(conn, "SELECT id, name FROM projects")}


def _prev_day(d: str) -> str:
    return (date.fromisoformat(d) - timedelta(days=1)).isoformat()


@router.get("/trial-balance")
def trial_balance(project_ids: str | None = Query(None), date_to: str | None = None, date_from: str | None = None):
    ids = _ids(project_ids)
    _, end = _period(None, date_to or date.today().isoformat())
    with get_db() as conn:
        entries = _journal(conn, ids, end)
    t = journal.totals(entries)
    rows = []
    for code in journal.ACCOUNTS:
        d, c = t.get(code, [0, 0])
        if not (d or c):
            continue
        net = d - c
        rows.append({**journal.account_info(code), "debits": d, "credits": c,
                     "debit": net if net > 0 else 0, "credit": -net if net < 0 else 0})
    td = sum(r["debit"] for r in rows)
    tc = sum(r["credit"] for r in rows)
    return {"as_of": end, "accounts": rows, "total_debit": td, "total_credit": tc,
            "balanced": td == tc, "entries": len(entries)}


@router.get("/general-ledger")
def general_ledger(project_ids: str | None = Query(None), account: str | None = None,
                   date_from: str | None = None, date_to: str | None = None):
    ids = _ids(project_ids)
    start, end = _period(date_from, date_to)
    if account and account not in journal.ACCOUNTS:
        raise HTTPException(400, "Unknown account")
    with get_db() as conn:
        entries = _journal(conn, ids, end)
        names = _project_names(conn)
    opening = journal.totals(entries, end=_prev_day(start)) if start > "1900-01-01" else {}
    period = journal.totals(entries, start=start)
    summary = []
    for code in journal.ACCOUNTS:
        o = journal.signed(code, *opening.get(code, [0, 0]))
        d, c = period.get(code, [0, 0])
        if not (o or d or c):
            continue
        summary.append({**journal.account_info(code), "opening": o, "debits": d, "credits": c,
                        "closing": o + journal.signed(code, d, c)})
    lines = []
    if account:
        bal = journal.signed(account, *opening.get(account, [0, 0]))
        for e in entries:
            if e["date"] < start:
                continue
            for a, d, c in e["lines"]:
                if a != account:
                    continue
                bal += journal.signed(account, d, c)
                lines.append({"date": e["date"], "ref": e["ref"], "narration": e["narration"], "party": e["party"],
                              "project_name": names.get(e["project_id"]), "debit": d, "credit": c, "balance": bal})
    return {"accounts": summary, "account": journal.account_info(account) if account else None,
            "opening": journal.signed(account, *opening.get(account, [0, 0])) if account else None,
            "lines": lines, "chart": [journal.account_info(c) for c in journal.ACCOUNTS]}


@router.get("/balance-sheet")
def balance_sheet(project_ids: str | None = Query(None), date_to: str | None = None, date_from: str | None = None):
    ids = _ids(project_ids)
    _, end = _period(None, date_to or date.today().isoformat())
    with get_db() as conn:
        entries = _journal(conn, ids, end)
    t = journal.totals(entries)
    sections = {"asset": [], "liability": [], "equity": []}
    profit = 0
    for code, (name, typ, group) in journal.ACCOUNTS.items():
        bal = journal.signed(code, *t.get(code, [0, 0]))
        if typ in ("income", "expense"):
            profit += bal if typ == "income" else -bal
            continue
        if bal:
            sections[typ].append({"code": code, "name": name, "group": group, "amount": bal})
    sections["equity"].append({"code": "RE", "name": "Retained earnings (profit to date)", "group": "Earnings",
                               "amount": profit})
    total = {k: sum(r["amount"] for r in v) for k, v in sections.items()}
    return {"as_of": end, "assets": sections["asset"], "liabilities": sections["liability"],
            "equity": sections["equity"], "total_assets": total["asset"], "total_liabilities": total["liability"],
            "total_equity": total["equity"], "profit_to_date": profit,
            "balanced": total["asset"] == total["liability"] + total["equity"]}


@router.get("/expense-ledger")
def expense_ledger(project_ids: str | None = Query(None), date_from: str | None = None, date_to: str | None = None):
    ids = _ids(project_ids)
    start, end = _period(date_from, date_to)
    with get_db() as conn:
        entries = _journal(conn, ids, end)
        names = _project_names(conn)
    rows = []
    for e in entries:
        if e["date"] < start:
            continue
        for a, d, c in e["lines"]:
            name, typ, group = journal.ACCOUNTS[a]
            if typ != "expense" or not (d - c):
                continue
            rows.append({"date": e["date"], "ref": e["ref"], "account": name, "group": group,
                         "category": e.get("category") or name, "narration": e["narration"], "party": e["party"],
                         "project_name": names.get(e["project_id"], "Company-wide"), "amount": d - c})
    by_cat: dict[str, dict] = {}
    by_proj: dict[str, dict] = {}
    monthly: dict[str, int] = {}
    for r in rows:
        for bucket, key in ((by_cat, r["category"]), (by_proj, r["project_name"])):
            x = bucket.setdefault(key, {"name": key, "amount": 0, "count": 0})
            x["amount"] += r["amount"]
            x["count"] += 1
        monthly[r["date"][:7]] = monthly.get(r["date"][:7], 0) + r["amount"]
    rows.sort(key=lambda r: r["date"], reverse=True)
    return {"total": sum(r["amount"] for r in rows), "count": len(rows), "rows": rows,
            "by_category": sorted(by_cat.values(), key=lambda x: -x["amount"]),
            "by_project": sorted(by_proj.values(), key=lambda x: -x["amount"]),
            "monthly": [{"month": k, "amount": v} for k, v in sorted(monthly.items())]}


@router.get("/monthly")
def monthly_in_out(project_ids: str | None = Query(None), date_from: str | None = None, date_to: str | None = None):
    ids = _ids(project_ids)
    start, end = _period(date_from, date_to)
    with get_db() as conn:
        entries = _journal(conn, ids, end)
    opening = 0
    months: dict[str, dict] = {}
    sources_in: dict[str, int] = {}
    sources_out: dict[str, int] = {}
    for e in entries:
        cash = sum(d - c for a, d, c in e["lines"] if a in journal.CASH_ACCOUNTS)
        if not cash:
            continue
        if e["date"] < start:
            opening += cash
            continue
        label = journal.SOURCE_LABEL.get(e["source"], e["source"].replace("_", " ").title())
        m = months.setdefault(e["date"][:7], {"month": e["date"][:7], "cash_in": 0, "cash_out": 0, "in": {}, "out": {}})
        side, agg = ("in", sources_in) if cash > 0 else ("out", sources_out)
        amt = abs(cash)
        m["cash_in" if cash > 0 else "cash_out"] += amt
        m[side][label] = m[side].get(label, 0) + amt
        agg[label] = agg.get(label, 0) + amt
    bal = opening
    rows = []
    for k in sorted(months):
        m = months[k]
        m["opening"] = bal
        m["net"] = m["cash_in"] - m["cash_out"]
        bal += m["net"]
        m["closing"] = bal
        rows.append(m)
    return {"opening": opening, "closing": bal, "months": rows,
            "total_in": sum(sources_in.values()), "total_out": sum(sources_out.values()),
            "in_sources": sorted(({"name": k, "amount": v} for k, v in sources_in.items()), key=lambda x: -x["amount"]),
            "out_sources": sorted(({"name": k, "amount": v} for k, v in sources_out.items()), key=lambda x: -x["amount"])}


@router.get("/project-wise")
def project_wise(project_ids: str | None = Query(None), date_from: str | None = None, date_to: str | None = None):
    ids = _ids(project_ids)
    start, end = _period(date_from, date_to)
    pf, pp = sql_in("p.id", ids)
    with get_db() as conn:
        inst_svc.refresh_statuses(conn)
        projects = fetch_all(conn, f"""SELECT p.id AS project_id, p.name AS project_name,
                   COALESCE(p.current_progress, 0) AS progress,
                   (SELECT COUNT(*) FROM units u WHERE u.project_id=p.id) AS units,
                   (SELECT COUNT(*) FROM units u WHERE u.project_id=p.id AND u.status='available') AS available
                   FROM projects p WHERE 1=1{pf} ORDER BY p.name""", pp) if _has_col(conn, "projects", "current_progress") \
            else fetch_all(conn, f"""SELECT p.id AS project_id, p.name AS project_name, 0 AS progress,
                   (SELECT COUNT(*) FROM units u WHERE u.project_id=p.id) AS units,
                   (SELECT COUNT(*) FROM units u WHERE u.project_id=p.id AND u.status='available') AS available
                   FROM projects p WHERE 1=1{pf} ORDER BY p.name""", pp)
        by = {p["project_id"]: p for p in projects}
        for p in projects:
            p.update(bookings=0, sales=0, collected=0, costs=0, commissions=0, other_income=0, cancellations=0,
                     receivable=0, overdue=0, budget=0, funding=0)
        entries = _journal(conn, ids, end)
        for e in entries:
            p = by.get(e["project_id"])
            if not p:
                continue
            for a, d, c in e["lines"]:
                if e["date"] >= start:
                    if a == "4000":
                        p["sales"] += c - d
                        p["bookings"] += 1
                    elif a == "4090":
                        p["cancellations"] += d - c
                    elif a in ("4100", "4200", "4300"):
                        p["other_income"] += c - d
                    elif a in ("5000", "5100"):
                        p["costs"] += d - c
                    elif a in ("5200", "5210"):
                        p["commissions"] += d - c
                    elif a in journal.CASH_ACCOUNTS and e["source"] == "payment":
                        p["collected"] += d - c
                    elif a == "2500" or a == "3000":
                        p["funding"] += c - d
        for r in fetch_all(conn, """SELECT u.project_id, COALESCE(SUM(i.remaining_amount),0) AS open_amt,
                                           COALESCE(SUM(CASE WHEN i.status IN ('overdue','partial') AND i.due_date < date('now')
                                                        THEN i.remaining_amount ELSE 0 END),0) AS overdue
                                    FROM installments i JOIN units u ON u.id=i.unit_id
                                    JOIN bookings b ON b.id=i.booking_id AND b.status='active'
                                    WHERE i.status IN ('pending','partial','overdue') GROUP BY u.project_id"""):
            if r["project_id"] in by:
                by[r["project_id"]].update(receivable=r["open_amt"], overdue=r["overdue"])
        for r in fetch_all(conn, "SELECT project_id, SUM(planned_amount) AS planned FROM project_budget_lines GROUP BY project_id"):
            if r["project_id"] in by:
                by[r["project_id"]]["budget"] = r["planned"] or 0
    for p in projects:
        p["sold"] = p["units"] - p["available"]
        p["net_sales"] = p["sales"] - p["cancellations"]
        p["margin"] = p["net_sales"] + p["other_income"] - p["costs"] - p["commissions"]
        p["collected_pct"] = round(p["collected"] / p["net_sales"] * 100) if p["net_sales"] > 0 else None
        p["budget_used_pct"] = round(p["costs"] / p["budget"] * 100) if p["budget"] else None
    keys = ("units", "sold", "available", "bookings", "sales", "cancellations", "net_sales", "collected",
            "receivable", "overdue", "costs", "commissions", "other_income", "margin", "budget", "funding")
    return {"projects": projects, "totals": {k: sum(p[k] for p in projects) for k in keys}}


def _has_col(conn, table: str, col: str) -> bool:
    return any(r[1] == col for r in conn.execute(f"PRAGMA table_info({table})"))


# ---------------------------------------------------------------- audit
AUDIT_FLAGS = {
    ("booking", "cancelled"): "Booking cancelled", ("purchase_order", "cancelled"): "Purchase order cancelled",
    ("booking", "transferred"): "Ownership transferred", ("unit", "status"): "Unit status changed manually",
    ("unit_hold", "expired"): "Hold expired",
}


@router.get("/audit")
def audit_report(date_from: str | None = None, date_to: str | None = None, project_ids: str | None = Query(None),
                 entity: str | None = None, limit: int = Query(2000, ge=1, le=5000)):
    start, end = _period(date_from, date_to)
    args: list = [start, end + " 23:59:59"]
    extra = ""
    if entity:
        extra = " AND entity_type=?"
        args.append(entity)
    with get_db() as conn:
        rows = fetch_all(conn, f"""SELECT id, entity_type, entity_id, action, details, created_at FROM audit_log
                                   WHERE created_at BETWEEN ? AND ?{extra} ORDER BY id DESC LIMIT ?""", (*args, limit))
        entities = [r["entity_type"] for r in fetch_all(conn, "SELECT DISTINCT entity_type FROM audit_log ORDER BY 1")]
        entries = _journal(conn, None, end)
        budget_rows = budget_svc.summary(conn)
    by_action: dict[str, dict] = {}
    daily: dict[str, int] = {}
    exceptions = []
    for r in rows:
        raw = r.get("details")
        try:
            det = json.loads(raw) if isinstance(raw, str) and raw else (raw or {})
        except ValueError:
            det = {"note": raw}
        r["details"] = ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in det.items()) if isinstance(det, dict) else str(det)
        key = f"{r['entity_type']} · {r['action']}"
        a = by_action.setdefault(key, {"name": key.replace("_", " "), "count": 0})
        a["count"] += 1
        daily[r["created_at"][:7]] = daily.get(r["created_at"][:7], 0) + 1
        flag = AUDIT_FLAGS.get((r["entity_type"], r["action"])) or ("Deleted record" if "delet" in r["action"] else None)
        if flag:
            exceptions.append({**r, "flag": flag})

    # Integrity checks on the books themselves.
    checks = []
    unbalanced = [e for e in entries if sum(d for _, d, _ in e["lines"]) != sum(c for *_, c in e["lines"])]
    checks.append({"check": "Every journal entry balances (debits = credits)", "ok": not unbalanced,
                   "detail": f"{len(entries)} entries checked" if not unbalanced else f"{len(unbalanced)} unbalanced"})
    t = journal.totals(entries)
    cash = {c: journal.signed(c, *t.get(c, [0, 0])) for c in journal.CASH_ACCOUNTS}
    neg = [journal.ACCOUNTS[c][0] for c, v in cash.items() if v < 0]
    checks.append({"check": "Cash and bank balances are not negative", "ok": not neg,
                   "detail": "OK" if not neg else f"Negative: {', '.join(neg)} — payments recorded without matching receipts"})
    over = [b for b in budget_rows if b["status"] == "Exceeded"]
    checks.append({"check": "No budget line is over budget", "ok": not over,
                   "detail": "OK" if not over else f"{len(over)} lines over: " + ", ".join(
                       f"{b['project_name']} / {b['category_name']}" for b in over[:4])})
    with get_db() as conn:
        overpaid = fetch_one(conn, """SELECT COUNT(*) n FROM installments WHERE paid_amount > amount""")["n"]
        cancelled_open = fetch_one(conn, """SELECT COUNT(*) n, COALESCE(SUM(i.remaining_amount),0) v FROM installments i
                                            JOIN bookings b ON b.id=i.booking_id
                                            WHERE b.status='cancelled' AND i.remaining_amount>0
                                              AND i.status IN ('pending','partial','overdue')""")
        after_cancel = fetch_one(conn, """SELECT COUNT(*) n FROM payments p JOIN booking_cancellations bc ON bc.booking_id=p.booking_id
                                          WHERE p.payment_date > date(bc.cancelled_at)""")["n"]
        no_receipt = fetch_one(conn, """SELECT COUNT(*) n FROM payments p WHERE NOT EXISTS
                                        (SELECT 1 FROM receipts r WHERE r.payment_id=p.id)""")["n"]
    checks.append({"check": "No installment is paid more than its amount", "ok": not overpaid,
                   "detail": "OK" if not overpaid else f"{overpaid} installments overpaid"})
    checks.append({"check": "Cancelled bookings have no open installments", "ok": not cancelled_open["n"],
                   "detail": "OK" if not cancelled_open["n"] else
                   f"{cancelled_open['n']} open installments (PKR {cancelled_open['v']:,}) still on cancelled bookings"})
    checks.append({"check": "No payments dated after a booking was cancelled", "ok": not after_cancel,
                   "detail": "OK" if not after_cancel else f"{after_cancel} payments"})
    checks.append({"check": "Every customer payment has a receipt", "ok": not no_receipt,
                   "detail": "OK" if not no_receipt else f"{no_receipt} payments without a receipt"})
    return {"events": rows, "count": len(rows), "entities": entities,
            "by_action": sorted(by_action.values(), key=lambda x: -x["count"]),
            "monthly": [{"month": k, "count": v} for k, v in sorted(daily.items())],
            "exceptions": exceptions, "checks": checks,
            "company_wide": True}
