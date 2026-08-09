from datetime import date

from backend.database import execute, fetch_all


def refresh_statuses(conn, booking_id: int | None = None):
    """Recompute installment status from paid amounts and due dates."""
    today = date.today().isoformat()
    params: tuple = ()
    where = ""
    if booking_id is not None:
        where = "WHERE booking_id=?"
        params = (booking_id,)

    rows = fetch_all(
        conn,
        f"SELECT id, amount, paid_amount, due_date, status FROM installments {where}",
        params,
    )
    for r in rows:
        if (r.get("status") or "").lower() == "cancelled":
            continue
        paid = r["paid_amount"] or 0
        amount = r["amount"]
        remaining = max(amount - paid, 0)
        if remaining <= 0:
            status = "paid"
        elif paid > 0:
            status = "partial"
        elif r["due_date"] < today:
            status = "overdue"
        else:
            status = "pending"
        execute(
            conn,
            "UPDATE installments SET remaining_amount=?, status=? WHERE id=?",
            (remaining, status, r["id"]),
        )


def list_for_booking(conn, booking_id: int) -> list[dict]:
    refresh_statuses(conn, booking_id)
    return fetch_all(
        conn,
        "SELECT * FROM installments WHERE booking_id=? ORDER BY installment_no, due_date",
        (booking_id,),
    )
