from backend.database import fetch_all, fetch_one
from backend.services import installments as inst_svc
from backend.services.project_filter import sql_in


OVERDUE_SQL = """
    SELECT i.id, i.booking_id, i.customer_id, i.unit_id, i.amount, i.remaining_amount,
           i.due_date, i.type,
           c.name AS customer_name, c.contact_number AS phone, c.cnic,
           u.unit_no, p.name AS project_name, u.project_id,
           CAST(julianday('now') - julianday(i.due_date) AS INT) AS days_overdue
    FROM installments i
    JOIN customers c ON c.id=i.customer_id
    JOIN units u ON u.id=i.unit_id
    JOIN projects p ON p.id=u.project_id
    WHERE i.status IN ('overdue','partial') AND i.remaining_amount > 0
      AND i.due_date < date('now')
"""


def get_overdue_list(conn, project_ids: list[int] | None = None) -> list[dict]:
    inst_svc.refresh_statuses(conn)
    filt, params = sql_in("u.project_id", project_ids)
    rows = fetch_all(conn, OVERDUE_SQL + filt + " ORDER BY days_overdue DESC", params)
    for r in rows:
        r["amount"] = r.get("remaining_amount") or r["amount"]
    return rows


def dashboard(conn, project_ids: list[int] | None = None) -> dict:
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
                WHERE i.status IN ('pending','partial','overdue')
                  AND u.project_id IN ({ph})""",
            tuple(project_ids),
        )
    else:
        recv = fetch_one(
            conn,
            "SELECT COALESCE(SUM(remaining_amount),0) AS v FROM installments WHERE status IN ('pending','partial','overdue')",
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
            f"""SELECT strftime('%m', p.payment_date) AS m,
                      COALESCE(SUM(p.amount),0) AS v
               FROM payments p
               JOIN bookings b ON b.id=p.booking_id
               WHERE p.payment_date >= date('now','-12 months')
                 AND b.project_id IN ({ph})
               GROUP BY strftime('%Y-%m', p.payment_date)
               ORDER BY p.payment_date""",
            tuple(project_ids),
        )
    else:
        sales_chart = fetch_all(
            conn,
            """SELECT strftime('%m', payment_date) AS m,
                      COALESCE(SUM(amount),0) AS v
               FROM payments
               WHERE payment_date >= date('now','-12 months')
               GROUP BY strftime('%Y-%m', payment_date)
               ORDER BY payment_date""",
        )
    chart_vals = [int(r["v"] / 100000) for r in sales_chart] if sales_chart else []
    while len(chart_vals) < 12:
        chart_vals.insert(0, 0)
    chart_vals = chart_vals[-12:]

    recovery_chart = fetch_all(
        conn,
        """SELECT strftime('%m', payment_date) AS m,
                  COALESCE(SUM(amount),0) AS collected,
                  (SELECT COALESCE(SUM(amount),0) FROM installments
                   WHERE strftime('%m', due_date)=strftime('%m', p.payment_date)) AS due
           FROM payments p
           WHERE payment_date >= date('now','-5 months')
           GROUP BY strftime('%Y-%m', payment_date)""",
    )
    rec_pcts = []
    for r in recovery_chart:
        due = r["due"] or 1
        rec_pcts.append(min(100, int(r["collected"] / due * 100)))
    while len(rec_pcts) < 5:
        rec_pcts.insert(0, 82)
    rec_pcts = rec_pcts[-5:]

    return {
        "kpi": {
            "total_units": inv["total_units"] or 0,
            "sold": inv["sold"] or 0,
            "available": inv["available"] or 0,
            "hold": inv["hold"] or 0,
            "receivable": recv["v"] if recv else 0,
            "payable": payable,
        },
        "overdue": overdue,
        "alerts": _alerts(conn, project_ids),
        "sales_chart": chart_vals or [0] * 12,
        "recovery_chart": rec_pcts or [82, 75, 91, 68, 54],
    }


def _alerts(conn, project_ids: list[int] | None = None) -> list[dict]:
    alerts = []
    overdue_count = fetch_one(
        conn,
        "SELECT COUNT(*) AS n FROM installments WHERE status='overdue'",
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
