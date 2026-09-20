from fastapi import APIRouter, Query
from backend.database import get_db, fetch_all, fetch_one
from backend.services import dashboard as dash_svc
from backend.services.project_filter import parse_project_ids, sql_in


def _due_soon(conn, project_ids: list[int] | None) -> list[dict]:
    clause, params = sql_in("u.project_id", project_ids)
    rows = fetch_all(
        conn,
        f"""SELECT i.id, i.booking_id, i.customer_id, i.unit_id, i.amount, i.remaining_amount,
                   i.paid_amount, i.due_date, i.type, i.notes, i.status,
                   i.trigger_kind, i.trigger_label, i.trigger_progress,
                   bk.booking_no,
                   c.name AS customer_name, c.contact_number AS phone, c.cnic,
                   u.unit_no, p.name AS project_name, u.project_id,
                   CAST(julianday(i.due_date) - julianday('now') AS INT) AS days_until,
                   (SELECT MAX(py.payment_date) FROM payments py WHERE py.booking_id=i.booking_id) AS last_payment
            FROM installments i
            JOIN bookings bk ON bk.id=i.booking_id AND bk.status='active'
            JOIN customers c ON c.id=i.customer_id
            JOIN units u ON u.id=i.unit_id
            JOIN projects p ON p.id=u.project_id
            WHERE i.status IN ('pending','partial') AND i.remaining_amount > 0
              AND i.due_date >= date('now')
              AND i.due_date < date('now','start of month','+1 month'){clause}
            ORDER BY i.due_date, c.name""",
        params,
    )
    for r in rows:
        r["original_amount"] = r.get("amount")
        r["amount"] = r.get("remaining_amount") or r["amount"]
        dash_svc.explain_installment(r, overdue=False)
    return rows

router = APIRouter(prefix="/api", tags=["recovery"])


def _ageing(overdue: list[dict]) -> dict:
    buckets = {
        "d30": {"count": 0, "amount": 0},
        "d60": {"count": 0, "amount": 0},
        "d90": {"count": 0, "amount": 0},
    }
    for row in overdue:
        days = row.get("days_overdue") or 0
        amt = row.get("amount") or 0
        if days <= 30:
            key = "d30"
        elif days <= 60:
            key = "d60"
        else:
            key = "d90"
        buckets[key]["count"] += 1
        buckets[key]["amount"] += amt
    return buckets


def _recovery(conn, project_ids: list[int] | None):
    overdue = dash_svc.get_overdue_list(conn, project_ids)
    if project_ids:
        ph = ",".join("?" * len(project_ids))
        totals = fetch_one(
            conn,
            f"""SELECT COALESCE(SUM(i.remaining_amount),0) AS receivable,
                      COALESCE(SUM(CASE WHEN i.status IN ('overdue','partial') AND i.due_date < date('now') THEN i.remaining_amount ELSE 0 END),0) AS overdue_amt
               FROM installments i
               JOIN units u ON u.id=i.unit_id
               JOIN bookings bk ON bk.id=i.booking_id AND bk.status='active'
               WHERE i.status IN ('pending','partial','overdue')
                 AND u.project_id IN ({ph})""",
            tuple(project_ids),
        )
        collected = fetch_one(
            conn,
            f"""SELECT COALESCE(SUM(p.amount),0) AS v FROM payments p
               JOIN bookings b ON b.id=p.booking_id
               WHERE p.payment_date >= date('now','-30 days')
                 AND b.project_id IN ({ph})""",
            tuple(project_ids),
        )
    else:
        totals = fetch_one(
            conn,
            """SELECT COALESCE(SUM(i.remaining_amount),0) AS receivable,
                      COALESCE(SUM(CASE WHEN i.status IN ('overdue','partial') AND i.due_date < date('now') THEN i.remaining_amount ELSE 0 END),0) AS overdue_amt
               FROM installments i JOIN bookings bk ON bk.id=i.booking_id AND bk.status='active'
               WHERE i.status IN ('pending','partial','overdue')""",
        )
        collected = fetch_one(
            conn,
            "SELECT COALESCE(SUM(amount),0) AS v FROM payments WHERE payment_date >= date('now','-30 days')",
        )
    return {
        "overdue": overdue,
        "due_soon": _due_soon(conn, project_ids),
        "receivable": totals["receivable"] if totals else 0,
        "overdue_amt": totals["overdue_amt"] if totals else 0,
        "collected_month": collected["v"] if collected else 0,
        "ageing": _ageing(overdue),
    }


@router.get("/recovery")
def recovery(
    project_id: int | None = Query(None),
    project_ids: str | None = Query(None),
):
    ids = parse_project_ids(project_ids, project_id)
    with get_db() as conn:
        return _recovery(conn, ids)


@router.get("/recovery/calendar")
def recovery_calendar(
    year: int = Query(...),
    month: int = Query(...),
    project_id: int | None = Query(None),
    project_ids: str | None = Query(None),
):
    ids = parse_project_ids(project_ids, project_id)
    start = f"{year:04d}-{month:02d}-01"
    if month == 12:
        end = f"{year + 1:04d}-01-01"
    else:
        end = f"{year:04d}-{month + 1:02d}-01"
    clause, params = sql_in("u.project_id", ids)
    q = f"""SELECT i.id, i.booking_id, i.customer_id, i.due_date, i.amount,
                   i.remaining_amount AS amount_due, i.status, i.type,
                   c.name AS customer_name, u.unit_no, p.name AS project_name,
                   c.contact_number AS phone
            FROM installments i
            JOIN bookings bk ON bk.id=i.booking_id AND bk.status='active'
            JOIN customers c ON c.id=i.customer_id
            JOIN units u ON u.id=i.unit_id
            JOIN projects p ON p.id=u.project_id
            WHERE i.status IN ('pending','partial','overdue')
              AND i.due_date>=? AND i.due_date<?{clause}
            ORDER BY i.due_date, c.name"""
    with get_db() as conn:
        rows = fetch_all(conn, q, (start, end) + params)
    days: dict = {}
    for r in rows:
        day = (r.get("due_date") or "")[:10]
        bucket = days.setdefault(day, {"date": day, "count": 0, "amount": 0, "items": []})
        due = r.get("amount_due") or r.get("amount") or 0
        bucket["count"] += 1
        bucket["amount"] += due
        r["amount"] = due
        bucket["items"].append(r)
    return {"year": year, "month": month, "days": list(days.values())}


@router.get("/demand-notices")
def demand_notices(
    project_id: int | None = Query(None),
    project_ids: str | None = Query(None),
):
    ids = parse_project_ids(project_ids, project_id)
    with get_db() as conn:
        return dash_svc.get_overdue_list(conn, ids)
