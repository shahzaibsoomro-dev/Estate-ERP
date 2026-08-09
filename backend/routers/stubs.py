from fastapi import APIRouter
from backend.database import fetch_all, fetch_one, get_db
from backend.services import installments as inst_svc

router = APIRouter(prefix="/api", tags=["stubs"])


@router.get("/reports/ageing")
def report_ageing():
    with get_db() as conn:
        inst_svc.refresh_statuses(conn)
        items = fetch_all(
            conn,
            """SELECT i.id, i.booking_id, i.customer_id, i.due_date, i.remaining_amount AS amount,
                      i.status, i.type,
                      c.name AS customer_name, u.unit_no, p.name AS project_name,
                      CAST(julianday('now') - julianday(i.due_date) AS INTEGER) AS days_overdue
               FROM installments i
               JOIN customers c ON c.id=i.customer_id
               JOIN units u ON u.id=i.unit_id
               JOIN projects p ON p.id=u.project_id
               WHERE i.status IN ('overdue','partial') AND i.remaining_amount > 0
                 AND i.due_date < date('now')
               ORDER BY days_overdue DESC, c.name""",
        )
        d30 = d60 = d90 = 0
        for r in items:
            days = r.get("days_overdue") or 0
            amt = r.get("amount") or 0
            if days <= 30:
                d30 += amt
            elif days <= 60:
                d60 += amt
            else:
                d90 += amt
        return {"d30": d30, "d60": d60, "d90": d90, "items": items}


@router.get("/reports/sales")
def report_sales():
    with get_db() as conn:
        return fetch_all(
            conn,
            """SELECT p.name AS project_name, COUNT(b.id) AS bookings,
                      COALESCE(SUM(b.final_sale_price),0) AS total_sales,
                      COALESCE(SUM(b.booking_amount),0) AS collected_dp
               FROM bookings b
               JOIN projects p ON p.id=b.project_id
               WHERE b.status='active'
               GROUP BY b.project_id""",
        )
