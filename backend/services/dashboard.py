from backend.database import fetch_all, fetch_one
from backend.services import installments as inst_svc
from datetime import date

from backend.services.project_filter import sql_in

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _last_12_months(by_ym: dict) -> list[dict]:
    """Zero-filled series for the 12 calendar months ending with the current one."""
    today = date.today()
    out = []
    for back in range(11, -1, -1):
        y, m = today.year, today.month - back
        while m <= 0:
            m += 12
            y -= 1
        ym = f"{y:04d}-{m:02d}"
        out.append({"ym": ym, "label": _MONTHS[m - 1], "year": y, "amount": by_ym.get(ym, 0) or 0})
    return out


OVERDUE_SQL = """
    SELECT i.id, i.booking_id, i.customer_id, i.unit_id, i.amount, i.remaining_amount,
           i.paid_amount, i.due_date, i.type, i.notes, i.status,
           i.trigger_kind, i.trigger_label, i.trigger_progress,
           bk.booking_no,
           c.name AS customer_name, c.contact_number AS phone, c.cnic,
           u.unit_no, p.name AS project_name, u.project_id,
           CAST(julianday('now') - julianday(i.due_date) AS INT) AS days_overdue,
           (SELECT MAX(py.payment_date) FROM payments py WHERE py.booking_id=i.booking_id) AS last_payment
    FROM installments i
    JOIN bookings bk ON bk.id=i.booking_id AND bk.status='active'
    JOIN customers c ON c.id=i.customer_id
    JOIN units u ON u.id=i.unit_id
    JOIN projects p ON p.id=u.project_id
    WHERE i.status IN ('overdue','partial') AND i.remaining_amount > 0
      AND i.due_date < date('now')
"""


def explain_installment(row: dict, *, overdue: bool = True) -> dict:
    """Plain-language why / when / what for demand notices and recovery."""
    original = row.get("original_amount")
    if original is None:
        original = row.get("amount") or 0
    remaining = row.get("remaining_amount")
    if remaining is None:
        remaining = row.get("amount") or 0
    paid = row.get("paid_amount") or 0
    due = row.get("due_date") or "—"
    typ = (row.get("trigger_label") or row.get("type") or "Installment").strip()
    construction = (row.get("trigger_kind") or "time") == "construction"
    if construction:
        pct = row.get("trigger_progress")
        why = (
            f"{typ} became payable when construction reached {pct}%."
            if pct is not None else
            f"{typ} became payable when its construction milestone was reached."
        )
    else:
        why = f"{typ} was due on {due}."
    if paid:
        what = f"PKR {int(remaining):,} still unpaid (PKR {int(paid):,} received of PKR {int(original):,})."
    elif overdue:
        what = f"PKR {int(remaining):,} was not received by the due date."
    else:
        what = f"PKR {int(remaining):,} is scheduled against this installment."
    if overdue:
        days = row.get("days_overdue") or 0
        when = f"{days} day{'s' if days != 1 else ''} overdue (due {due})"
    else:
        days = row.get("days_until")
        when = f"Due {due}"
        if days is not None:
            if days == 0:
                when += " · due today"
            elif days > 0:
                when += f" · in {days} day{'s' if days != 1 else ''}"
    row["original_amount"] = original
    row["why"] = why
    row["what"] = what
    row["when"] = when
    row["reason"] = f"{why} {what}".strip()
    return row


def get_overdue_list(conn, project_ids: list[int] | None = None) -> list[dict]:
    inst_svc.refresh_statuses(conn)
    filt, params = sql_in("u.project_id", project_ids)
    rows = fetch_all(conn, OVERDUE_SQL + filt + " ORDER BY days_overdue DESC", params)
    for r in rows:
        r["original_amount"] = r.get("amount")
        r["amount"] = r.get("remaining_amount") or r["amount"]
        explain_installment(r, overdue=True)
    return rows


def dashboard(conn, project_ids: list[int] | None = None) -> dict:
    from backend.services import holds as holds_svc
    holds_svc.expire_due_holds(conn)
    inst_svc.refresh_statuses(conn)

    unit_filt, unit_params = sql_in("project_id", project_ids)
    inv = fetch_one(
        conn,
        f"""SELECT COUNT(*) AS total_units,
                   SUM(CASE WHEN status IN ('sold','booked','possession_delivered') THEN 1 ELSE 0 END) AS sold,
                   SUM(CASE WHEN status='available' THEN 1 ELSE 0 END) AS available,
                   SUM(CASE WHEN status='hold' THEN 1 ELSE 0 END) AS hold
            FROM units WHERE 1=1{unit_filt}""",
        unit_params,
    )

    if project_ids:
        ph = ",".join("?" * len(project_ids))
        recv = fetch_one(
            conn,
            f"""SELECT COALESCE(SUM(i.remaining_amount),0) AS v
                FROM installments i
                JOIN units u ON u.id=i.unit_id
                JOIN bookings bk ON bk.id=i.booking_id AND bk.status='active'
                WHERE i.status IN ('pending','partial','overdue')
                  AND u.project_id IN ({ph})""",
            tuple(project_ids),
        )
    else:
        recv = fetch_one(
            conn,
            "SELECT COALESCE(SUM(i.remaining_amount),0) AS v FROM installments i JOIN bookings bk ON bk.id=i.booking_id AND bk.status='active' WHERE i.status IN ('pending','partial','overdue')",
        )

    if project_ids:
        ph = ",".join("?" * len(project_ids))
        po_tot = fetch_one(
            conn,
            f"""SELECT COALESCE(SUM(total),0) AS v FROM purchase_orders
                WHERE status != 'cancelled' AND project_id IN ({ph})""",
            tuple(project_ids),
        )
        vp_paid = fetch_one(
            conn,
            f"""SELECT COALESCE(SUM(vp.amount),0) AS v FROM vendor_payments vp
                JOIN purchase_orders po ON po.id=vp.purchase_order_id
                WHERE po.project_id IN ({ph})""",
            tuple(project_ids),
        )
    else:
        po_tot = fetch_one(
            conn,
            "SELECT COALESCE(SUM(total),0) AS v FROM purchase_orders WHERE status != 'cancelled'",
        )
        vp_paid = fetch_one(
            conn, "SELECT COALESCE(SUM(amount),0) AS v FROM vendor_payments",
        )
    vendor_bal = (po_tot["v"] if po_tot else 0) - (vp_paid["v"] if vp_paid else 0)
    agent_unpaid = fetch_one(
        conn,
        """SELECT COALESCE(SUM(commission_amount - paid_amount),0) AS v
           FROM agent_commissions
           WHERE status != 'reversed' AND paid_amount < commission_amount""",
    )
    payable = vendor_bal + (agent_unpaid["v"] if agent_unpaid else 0)

    overdue = get_overdue_list(conn, project_ids)

    if project_ids:
        ph = ",".join("?" * len(project_ids))
        sales_chart = fetch_all(
            conn,
            f"""SELECT strftime('%Y-%m', p.payment_date) AS ym,
                      COALESCE(SUM(p.amount),0) AS v
               FROM payments p
               JOIN bookings b ON b.id=p.booking_id
               WHERE p.payment_date >= date('now','start of month','-11 months')
                 AND b.project_id IN ({ph})
               GROUP BY strftime('%Y-%m', p.payment_date)
               ORDER BY p.payment_date""",
            tuple(project_ids),
        )
    else:
        sales_chart = fetch_all(
            conn,
            """SELECT strftime('%Y-%m', payment_date) AS ym,
                      COALESCE(SUM(amount),0) AS v
               FROM payments
               WHERE payment_date >= date('now','start of month','-11 months')
               GROUP BY strftime('%Y-%m', payment_date)
               ORDER BY payment_date""",
        )
    sales_series = _last_12_months({r["ym"]: r["v"] for r in sales_chart})
    chart_vals = [int(m["amount"] / 100000) for m in sales_series]

    # Collection rate: due installments vs collections in each of last 5 months (project-scoped)
    due_filt, due_params = sql_in("u.project_id", project_ids)
    pay_filt, pay_params = sql_in("b.project_id", project_ids)
    months = fetch_all(
        conn,
        """SELECT strftime('%Y-%m', date('now', '-' || n || ' months')) AS ym
           FROM (SELECT 0 AS n UNION ALL SELECT 1 UNION ALL SELECT 2
                 UNION ALL SELECT 3 UNION ALL SELECT 4)""",
    )
    months = [m["ym"] for m in months]
    months.reverse()  # oldest → newest
    rec_pcts = []
    for ym in months:
        due_row = fetch_one(
            conn,
            f"""SELECT COALESCE(SUM(i.amount),0) AS v
                FROM installments i
                JOIN units u ON u.id=i.unit_id
                WHERE strftime('%Y-%m', i.due_date)=?
                  AND i.status != 'scheduled'
                  {due_filt}""",
            (ym, *due_params),
        )
        coll_row = fetch_one(
            conn,
            f"""SELECT COALESCE(SUM(p.amount),0) AS v
                FROM payments p
                LEFT JOIN bookings b ON b.id=p.booking_id
                WHERE strftime('%Y-%m', p.payment_date)=?
                  AND NOT EXISTS (
                    SELECT 1 FROM hold_token_applications hta WHERE hta.payment_id=p.id
                  )
                  {pay_filt}""",
            (ym, *pay_params),
        )
        due = int(due_row["v"] if due_row else 0)
        collected = int(coll_row["v"] if coll_row else 0)
        if due > 0:
            rec_pcts.append(min(100, int(round(collected / due * 100))))
        elif collected > 0:
            rec_pcts.append(100)
        else:
            rec_pcts.append(0)

    # Overall collection rate (lifetime in scope): collected / (collected + remaining due)
    if project_ids:
        ph = ",".join("?" * len(project_ids))
        overall_coll = fetch_one(
            conn,
            f"""SELECT COALESCE(SUM(p.amount),0) AS v FROM payments p
                JOIN bookings b ON b.id=p.booking_id
                WHERE b.project_id IN ({ph})
                  AND NOT EXISTS (
                    SELECT 1 FROM hold_token_applications hta WHERE hta.payment_id=p.id
                  )""",
            tuple(project_ids),
        )
        overall_remain = fetch_one(
            conn,
            f"""SELECT COALESCE(SUM(i.remaining_amount),0) AS v
                FROM installments i JOIN units u ON u.id=i.unit_id
                JOIN bookings bk ON bk.id=i.booking_id AND bk.status='active'
                WHERE i.status IN ('pending','partial','overdue','paid')
                  AND u.project_id IN ({ph})""",
            tuple(project_ids),
        )
    else:
        overall_coll = fetch_one(
            conn,
            """SELECT COALESCE(SUM(p.amount),0) AS v FROM payments p
               WHERE NOT EXISTS (
                 SELECT 1 FROM hold_token_applications hta WHERE hta.payment_id=p.id
               )""",
        )
        overall_remain = fetch_one(
            conn,
            """SELECT COALESCE(SUM(i.remaining_amount),0) AS v FROM installments i
               JOIN bookings bk ON bk.id=i.booking_id AND bk.status='active'
               WHERE i.status IN ('pending','partial','overdue','paid')""",
        )
    coll_total = int(overall_coll["v"] if overall_coll else 0)
    remain_total = int(overall_remain["v"] if overall_remain else 0)
    billed = coll_total + remain_total
    collection_rate = min(100, int(round(coll_total / billed * 100))) if billed > 0 else 0

    return {
        "kpi": {
            "total_units": inv["total_units"] or 0,
            "sold": inv["sold"] or 0,
            "available": inv["available"] or 0,
            "hold": inv["hold"] or 0,
            "receivable": recv["v"] if recv else 0,
            "payable": payable,
            "collection_rate": collection_rate,
            "collected_total": coll_total,
            "billed_total": billed,
        },
        "overdue": overdue,
        "alerts": _alerts(conn, project_ids),
        "sales_chart": chart_vals or [0] * 12,
        "sales_series": sales_series,
        "recovery_chart": rec_pcts,
        "recovery_months": months,
    }


def _alerts(conn, project_ids: list[int] | None = None) -> list[dict]:
    alerts = []
    overdue_count = fetch_one(
        conn,
        "SELECT COUNT(*) AS n FROM installments i JOIN bookings bk ON bk.id=i.booking_id AND bk.status='active' WHERE i.status='overdue'",
    )
    if overdue_count and overdue_count["n"] > 0:
        alerts.append({
            "type": "warning",
            "title": f"{overdue_count['n']} overdue installments",
            "sub": "Review Recovery module",
        })
    budget_over = fetch_all(
        conn,
        f"""SELECT p.name, bc.name AS cat, bl.planned_amount,
                  (SELECT COALESCE(SUM(total),0) FROM purchase_orders po
                   WHERE po.project_id=bl.project_id AND po.budget_category_id=bl.category_id) AS spent
           FROM project_budget_lines bl
           JOIN projects p ON p.id=bl.project_id
           JOIN budget_categories bc ON bc.id=bl.category_id
           WHERE bl.is_active=1{sql_in('bl.project_id', project_ids)[0]}""",
        sql_in("bl.project_id", project_ids)[1],
    )
    for b in budget_over:
        if b["planned_amount"] and b["spent"] > b["planned_amount"]:
            pct = int((b["spent"] / b["planned_amount"] - 1) * 100)
            alerts.append({
                "type": "danger",
                "title": f"Budget overrun — {b['cat']}",
                "sub": f"{b['name']} exceeded by {pct}%",
            })
    if not alerts:
        alerts.append({
            "type": "success",
            "title": "All systems normal",
            "sub": "No critical alerts",
        })
    return alerts[:6]
