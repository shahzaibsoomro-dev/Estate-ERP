from datetime import date

from backend.database import fetch_all, fetch_one
from backend.services import audit as audit_svc
from backend.services import installments as inst_svc
from backend.services import settings as settings_svc


def _next_receipt_no(conn) -> str:
    prefix = settings_svc.get(conn, "receipt_prefix", "RCP")
    rows = fetch_all(conn, "SELECT receipt_no FROM receipts WHERE receipt_no LIKE ?", (f"{prefix}-%",))
    best = 1000
    for r in rows:
        try:
            best = max(best, int(str(r["receipt_no"]).split("-")[-1]))
        except (TypeError, ValueError):
            pass
    return f"{prefix}-{best + 1}"


def record_payment(conn, data: dict) -> dict:
    installment_id = data.get("installment_id")
    amount = data["amount"]
    booking_id = data["booking_id"]
    customer_id = data["customer_id"]
    payment_date = data.get("paid_date") or data.get("payment_date") or date.today().isoformat()

    if installment_id:
        inst = fetch_one(conn, "SELECT * FROM installments WHERE id=?", (installment_id,))
        if not inst:
            raise ValueError("Installment not found")
        if amount > inst["remaining_amount"]:
            raise ValueError("Payment exceeds remaining installment amount")

    cur = conn.execute(
        """INSERT INTO payments(customer_id, booking_id, installment_id, amount,
           payment_date, payment_method, bank, reference_number, received_by, notes)
           VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (
            customer_id, booking_id, installment_id, amount, payment_date,
            data.get("method") or data.get("payment_method", "Cash"),
            data.get("bank"), data.get("reference_number"),
            data.get("received_by", "Admin"), data.get("notes"),
        ),
    )
    payment_id = cur.lastrowid
    receipt_no = _next_receipt_no(conn)
    conn.execute(
        "INSERT INTO receipts(payment_id, receipt_no) VALUES(?, ?)",
        (payment_id, receipt_no),
    )

    if installment_id:
        inst = fetch_one(conn, "SELECT * FROM installments WHERE id=?", (installment_id,))
        new_paid = (inst["paid_amount"] or 0) + amount
        remaining = max(inst["amount"] - new_paid, 0)
        conn.execute(
            "UPDATE installments SET paid_amount=?, remaining_amount=? WHERE id=?",
            (new_paid, remaining, installment_id),
        )
    else:
        left = amount
        insts = fetch_all(
            conn,
            """SELECT id, amount, paid_amount, remaining_amount FROM installments
               WHERE booking_id=? AND status != 'cancelled' AND remaining_amount > 0
               ORDER BY due_date, installment_no""",
            (booking_id,),
        )
        for inst in insts:
            if left <= 0:
                break
            take = min(left, inst["remaining_amount"] or 0)
            if take < 1:
                continue
            new_paid = (inst["paid_amount"] or 0) + take
            remaining = max((inst["amount"] or 0) - new_paid, 0)
            conn.execute(
                "UPDATE installments SET paid_amount=?, remaining_amount=? WHERE id=?",
                (new_paid, remaining, inst["id"]),
            )
            left -= take
    inst_svc.refresh_statuses(conn, booking_id)

    audit_svc.log(conn, "payment", payment_id, "recorded", {
        "amount": amount, "receipt_no": receipt_no, "installment_id": installment_id,
    })
    return {"ok": True, "receipt": receipt_no, "payment_id": payment_id}
