from datetime import date

from backend.database import fetch_all, fetch_one
from backend.services import installments as inst_svc
from backend.services.units import get_unit


def _days_overdue(due_date: str | None, status: str | None) -> int:
    if not due_date or status not in ("overdue", "partial"):
        return 0
    try:
        delta = (date.today() - date.fromisoformat(due_date[:10])).days
        return max(delta, 0)
    except ValueError:
        return 0


def list_portal_customers(conn) -> list[dict]:
    return fetch_all(
        conn,
        """SELECT c.id, c.name, c.cnic, c.contact_number AS phone,
                  COUNT(b.id) AS booking_count
           FROM customers c
           JOIN bookings b ON b.customer_id=c.id AND b.status='active'
           GROUP BY c.id
           ORDER BY c.name""",
    )


def get_portal(conn, customer_id: int) -> dict | None:
    customer = fetch_one(
        conn,
        """SELECT id, name, father_name, cnic, contact_number AS phone,
                  email, residential_address AS address
           FROM customers WHERE id=?""",
        (customer_id,),
    )
    if not customer:
        return None

    bookings = fetch_all(
        conn,
        """SELECT b.id, b.booking_no, b.booking_date, b.final_sale_price, b.booking_amount,
                  b.status, b.unit_id, b.project_id, b.possession_date,
                  u.unit_no, p.name AS project_name, p.location AS project_location
           FROM bookings b
           JOIN units u ON u.id=b.unit_id
           JOIN projects p ON p.id=b.project_id
           WHERE b.customer_id=? AND b.status='active'
           ORDER BY b.booking_date DESC, b.id DESC""",
        (customer_id,),
    )

    result = []
    for b in bookings:
        inst_svc.refresh_statuses(conn, b["id"])
        installments = fetch_all(
            conn,
            """SELECT id, installment_no, type, due_date, amount, paid_amount,
                      remaining_amount, status
               FROM installments WHERE booking_id=?
               ORDER BY installment_no, due_date""",
            (b["id"],),
        )
        for inst in installments:
            inst["days_overdue"] = _days_overdue(inst.get("due_date"), inst.get("status"))
        payments = fetch_all(
            conn,
            """SELECT py.id, py.amount, py.payment_date, py.payment_method, py.reference_number,
                      py.notes, r.receipt_no, i.type AS inst_type
               FROM payments py
               LEFT JOIN receipts r ON r.payment_id=py.id
               LEFT JOIN installments i ON i.id=py.installment_id
               WHERE py.booking_id=?
               ORDER BY py.payment_date DESC, py.id DESC""",
            (b["id"],),
        )
        total_paid = sum(p["amount"] or 0 for p in payments)
        sale_price = b.get("final_sale_price") or 0
        outstanding = max(sale_price - total_paid, 0)
        unit = get_unit(conn, b["unit_id"]) or {}
        result.append({
            "id": b["id"],
            "booking_no": b["booking_no"],
            "booking_date": b["booking_date"],
            "status": b["status"],
            "unit_id": b["unit_id"],
            "unit_no": b["unit_no"],
            "project_id": b["project_id"],
            "project_name": b["project_name"],
            "project_location": b["project_location"],
            "possession_date": b["possession_date"],
            "unit": unit,
            "installments": installments,
            "payments": payments,
            "summary": {
                "sale_price": sale_price,
                "total_paid": total_paid,
                "outstanding": outstanding,
                "pct_paid": round(total_paid / sale_price * 100) if sale_price else 0,
            },
        })

    return {"customer": customer, "bookings": result}
