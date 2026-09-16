"""Unit hold tokens, receipts, refunds, and booking conversion."""

from datetime import date, timedelta

from backend.database import fetch_all, fetch_one
from backend.services import audit as audit_svc
from backend.services import payments as pay_svc
from backend.services import settings as settings_svc


def _clean(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _next_doc_no(conn, prefix: str) -> str:
    """Max-suffix across payment receipts, hold receipts, and hold vouchers."""
    best = 1000
    like = f"{prefix}-%"
    for sql, col in (
        ("SELECT receipt_no AS n FROM receipts WHERE receipt_no LIKE ?", "n"),
        ("SELECT receipt_no AS n FROM hold_receipts WHERE receipt_no LIKE ?", "n"),
        ("SELECT voucher_no AS n FROM hold_transactions WHERE voucher_no LIKE ?", "n"),
    ):
        try:
            rows = fetch_all(conn, sql, (like,))
        except Exception:
            continue
        for r in rows:
            try:
                best = max(best, int(str(r[col]).split("-")[-1]))
            except (TypeError, ValueError, KeyError):
                pass
    return f"{prefix}-{best + 1}"


def _next_hold_receipt_no(conn) -> str:
    prefix = settings_svc.get(conn, "receipt_prefix", "RCP")
    return _next_doc_no(conn, prefix)


def _next_refund_voucher(conn) -> str:
    return _next_doc_no(conn, "HRF")


def get_active_hold(conn, unit_id: int) -> dict | None:
    expire_due_holds(conn, unit_id=unit_id)
    return fetch_one(
        conn,
        """SELECT h.*, c.name AS customer_name, c.cnic AS customer_cnic,
                  c.contact_number AS customer_phone
           FROM unit_holds h
           LEFT JOIN customers c ON c.id=h.customer_id
           WHERE h.unit_id=? AND h.status='active'
           ORDER BY h.id DESC LIMIT 1""",
        (unit_id,),
    )


def get_hold(conn, hold_id: int) -> dict | None:
    return fetch_one(
        conn,
        """SELECT h.*, c.name AS customer_name, u.unit_no, p.name AS project_name
           FROM unit_holds h
           LEFT JOIN customers c ON c.id=h.customer_id
           JOIN units u ON u.id=h.unit_id
           JOIN projects p ON p.id=u.project_id
           WHERE h.id=?""",
        (hold_id,),
    )


def hold_history(conn, unit_id: int) -> list[dict]:
    holds = fetch_all(
        conn,
        """SELECT h.*, c.name AS customer_name
           FROM unit_holds h
           LEFT JOIN customers c ON c.id=h.customer_id
           WHERE h.unit_id=?
           ORDER BY h.id DESC""",
        (unit_id,),
    )
    out = []
    for h in holds:
        item = dict(h)
        item["receipts"] = fetch_all(
            conn,
            "SELECT * FROM hold_receipts WHERE hold_id=? ORDER BY id",
            (h["id"],),
        )
        item["transactions"] = fetch_all(
            conn,
            "SELECT * FROM hold_transactions WHERE hold_id=? ORDER BY id",
            (h["id"],),
        )
        item["applications"] = fetch_all(
            conn,
            "SELECT * FROM hold_token_applications WHERE hold_id=? ORDER BY id",
            (h["id"],),
        )
        out.append(item)
    return out


def unapplied_token(conn, hold_id: int) -> int:
    inn = fetch_one(
        conn,
        """SELECT COALESCE(SUM(amount),0) AS v FROM hold_transactions
           WHERE hold_id=? AND direction='in'""",
        (hold_id,),
    )
    out = fetch_one(
        conn,
        """SELECT COALESCE(SUM(amount),0) AS v FROM hold_transactions
           WHERE hold_id=? AND direction='refund'""",
        (hold_id,),
    )
    applied = fetch_one(
        conn,
        "SELECT COALESCE(SUM(amount),0) AS v FROM hold_token_applications WHERE hold_id=?",
        (hold_id,),
    )
    return max((inn["v"] if inn else 0) - (out["v"] if out else 0) - (applied["v"] if applied else 0), 0)


def create_hold(conn, unit_id: int, data: dict) -> dict:
    expire_due_holds(conn, unit_id=unit_id)
    unit = fetch_one(conn, "SELECT * FROM units WHERE id=?", (unit_id,))
    if not unit:
        raise ValueError("Unit not found")
    if unit["status"] == "hold" or fetch_one(
        conn, "SELECT id FROM unit_holds WHERE unit_id=? AND status='active'", (unit_id,),
    ):
        raise ValueError("Unit already has an active hold")
    if unit["status"] not in ("available",):
        raise ValueError(f"Unit is not available for hold (status: {unit['status']})")
    if fetch_one(conn, "SELECT id FROM bookings WHERE unit_id=? AND status='active'", (unit_id,)):
        raise ValueError("Unit has an active booking")

    token = max(_int(data.get("token_amount") or data.get("token") or 0), 0)
    customer_id = data.get("customer_id") or data.get("hold_customer_id")
    if customer_id is not None:
        customer_id = int(customer_id)
        if not fetch_one(conn, "SELECT id FROM customers WHERE id=?", (customer_id,)):
            raise ValueError("Customer not found — register the customer first")
    if token > 0 and not customer_id:
        raise ValueError("Positive hold token requires a registered customer")

    hold_until = _clean(data.get("hold_until"))
    notes = _clean(data.get("notes") or data.get("hold_notes"))
    held_at = _clean(data.get("held_at") or data.get("receipt_date")) or date.today().isoformat()
    method = _clean(data.get("payment_method") or data.get("method")) or "Cash"
    bank = _clean(data.get("bank"))
    reference = _clean(data.get("reference_number"))
    received_by = _clean(data.get("received_by")) or "Admin"

    cur = conn.execute(
        """INSERT INTO unit_holds(unit_id, customer_id, hold_until, notes, status,
           token_amount, held_at)
           VALUES(?,?,?,?, 'active', ?, ?)""",
        (unit_id, customer_id, hold_until, notes, token, held_at),
    )
    hold_id = cur.lastrowid

    txn_id = None
    if token > 0:
        cur_tx = conn.execute(
            """INSERT INTO hold_transactions(
                 hold_id, direction, amount, txn_date, payment_method, bank,
                 reference_number, received_by, notes)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (
                hold_id, "in", token, held_at, method, bank, reference,
                received_by, notes or "Hold token received",
            ),
        )
        txn_id = cur_tx.lastrowid

    receipt_no = _next_hold_receipt_no(conn)
    ack_note = (
        "Hold acknowledgement — no money received"
        if token <= 0
        else "Hold token receipt"
    )
    conn.execute(
        """INSERT INTO hold_receipts(hold_id, receipt_no, acknowledged_amount, transaction_id, notes)
           VALUES(?,?,?,?,?)""",
        (hold_id, receipt_no, token, txn_id, ack_note),
    )

    conn.execute(
        """UPDATE units SET status='hold', hold_customer_id=?, hold_until=?, hold_notes=?
           WHERE id=?""",
        (customer_id, hold_until, notes, unit_id),
    )
    audit_svc.log(conn, "unit_hold", hold_id, "created", {
        "unit_id": unit_id, "token_amount": token, "receipt_no": receipt_no,
    })
    return hold_detail(conn, hold_id)


def hold_detail(conn, hold_id: int) -> dict:
    hold = get_hold(conn, hold_id)
    if not hold:
        raise ValueError("Hold not found")
    receipts = fetch_all(conn, "SELECT * FROM hold_receipts WHERE hold_id=? ORDER BY id", (hold_id,))
    transactions = fetch_all(
        conn, "SELECT * FROM hold_transactions WHERE hold_id=? ORDER BY id", (hold_id,),
    )
    applications = fetch_all(
        conn, "SELECT * FROM hold_token_applications WHERE hold_id=? ORDER BY id", (hold_id,),
    )
    return {
        "hold": hold,
        "receipts": receipts,
        "transactions": transactions,
        "applications": applications,
        "unapplied_token": unapplied_token(conn, hold_id),
        "receipt": receipts[0] if receipts else None,
    }


def _post_refund(conn, hold_id: int, reason: str) -> dict | None:
    amount = unapplied_token(conn, hold_id)
    if amount <= 0:
        return None
    hold = get_hold(conn, hold_id)
    voucher = _next_refund_voucher(conn)
    today = date.today().isoformat()
    cur = conn.execute(
        """INSERT INTO hold_transactions(
             hold_id, direction, amount, txn_date, payment_method, received_by,
             notes, voucher_no)
           VALUES(?,?,?,?, 'Cash', 'Admin', ?, ?)""",
        (hold_id, "refund", amount, today, reason or "Hold refund", voucher),
    )
    # Refund acknowledgement under hold_receipts for audit trail
    receipt_no = _next_hold_receipt_no(conn)
    conn.execute(
        """INSERT INTO hold_receipts(hold_id, receipt_no, acknowledged_amount, transaction_id, notes)
           VALUES(?,?,?,?,?)""",
        (hold_id, receipt_no, amount, cur.lastrowid, f"Refund · {voucher}"),
    )
    return {"amount": amount, "voucher_no": voucher, "receipt_no": receipt_no}


def release_hold(conn, hold_id: int, reason: str | None = None, *, as_expired: bool = False) -> dict:
    hold = fetch_one(conn, "SELECT * FROM unit_holds WHERE id=?", (hold_id,))
    if not hold:
        raise ValueError("Hold not found")
    if hold["status"] != "active":
        raise ValueError(f"Hold is not active (status: {hold['status']})")

    status = "expired" if as_expired else "released"
    reason_text = _clean(reason) or ("Hold expired" if as_expired else "Hold released")
    refund = _post_refund(conn, hold_id, reason_text)

    conn.execute(
        """UPDATE unit_holds SET status=?, released_at=date('now'), release_reason=?
           WHERE id=?""",
        (status, reason_text, hold_id),
    )
    conn.execute(
        """UPDATE units SET status='available', hold_customer_id=NULL, hold_until=NULL, hold_notes=NULL
           WHERE id=?""",
        (hold["unit_id"],),
    )
    audit_svc.log(conn, "unit_hold", hold_id, status, {
        "refund": refund["amount"] if refund else 0,
        "reason": reason_text,
    })
    detail = hold_detail(conn, hold_id)
    detail["refund"] = refund
    return detail


def expire_due_holds(conn, unit_id: int | None = None) -> list[dict]:
    """Auto-refund and close holds past hold_until. Called on list/read paths."""
    today = date.today().isoformat()
    q = """SELECT id FROM unit_holds
           WHERE status='active' AND hold_until IS NOT NULL AND hold_until < ?"""
    params: list = [today]
    if unit_id is not None:
        q += " AND unit_id=?"
        params.append(unit_id)
    due = fetch_all(conn, q, tuple(params))
    results = []
    for row in due:
        try:
            results.append(release_hold(conn, row["id"], "Hold expired", as_expired=True))
        except ValueError:
            continue
    return results


def convert_hold_to_booking(conn, unit_id: int, booking_id: int, customer_id: int) -> dict | None:
    """Mark active hold converted and apply unapplied token as a booking payment."""
    hold = fetch_one(
        conn,
        "SELECT * FROM unit_holds WHERE unit_id=? AND status='active' ORDER BY id DESC LIMIT 1",
        (unit_id,),
    )
    if not hold:
        return None
    if hold.get("customer_id") and int(hold["customer_id"]) != int(customer_id):
        raise ValueError("Booking customer must match the customer holding this unit")

    token = unapplied_token(conn, hold["id"])
    payment_id = None
    if token > 0:
        pay = pay_svc.record_payment(conn, {
            "booking_id": booking_id,
            "customer_id": customer_id,
            "amount": token,
            "payment_date": date.today().isoformat(),
            "method": "Hold Token",
            "notes": f"Applied from hold #{hold['id']}",
            "received_by": "Admin",
        })
        payment_id = pay["payment_id"]
        conn.execute(
            """INSERT INTO hold_token_applications(hold_id, booking_id, payment_id, amount)
               VALUES(?,?,?,?)""",
            (hold["id"], booking_id, payment_id, token),
        )

    conn.execute(
        """UPDATE unit_holds SET status='converted', released_at=date('now'),
           release_reason=?, converted_booking_id=? WHERE id=?""",
        ("Converted to booking", booking_id, hold["id"]),
    )
    conn.execute(
        """UPDATE units SET hold_customer_id=NULL, hold_until=NULL, hold_notes=NULL WHERE id=?""",
        (unit_id,),
    )
    audit_svc.log(conn, "unit_hold", hold["id"], "converted", {
        "booking_id": booking_id, "token_applied": token, "payment_id": payment_id,
    })
    return {"hold_id": hold["id"], "token_applied": token, "payment_id": payment_id}


def assert_booking_customer_ok(conn, unit: dict, customer_id: int) -> None:
    if unit.get("status") != "hold":
        return
    hold = fetch_one(
        conn,
        "SELECT * FROM unit_holds WHERE unit_id=? AND status='active' ORDER BY id DESC LIMIT 1",
        (unit["id"],),
    )
    held_cust = None
    if hold and hold.get("customer_id"):
        held_cust = int(hold["customer_id"])
    elif unit.get("hold_customer_id"):
        held_cust = int(unit["hold_customer_id"])
    if held_cust is not None and int(customer_id) != held_cust:
        raise ValueError("This unit is on hold for another customer")
