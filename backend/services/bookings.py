from datetime import date

from backend.database import fetch_all, fetch_one
from backend.services import audit as audit_svc
from backend.services import installments as inst_svc
from backend.services import settings as settings_svc


def _next_booking_no(conn) -> str:
    rows = fetch_all(conn, "SELECT booking_no FROM bookings WHERE booking_no LIKE 'BK-%'")
    best = 1000
    for r in rows:
        try:
            best = max(best, int(str(r["booking_no"]).split("-")[-1]))
        except (TypeError, ValueError):
            pass
    return f"BK-{best + 1}"


def _resolve_agent_id(conn, agent_name: str | None) -> int | None:
    if not agent_name or agent_name.lower().startswith("none"):
        return None
    name = agent_name.split("(")[0].strip()
    ag = fetch_one(conn, "SELECT id FROM agents WHERE name=?", (name,))
    return ag["id"] if ag else None


def create_booking(conn, data: dict) -> dict:
    unit = fetch_one(conn, "SELECT * FROM units WHERE id=?", (data["unit_id"],))
    if not unit:
        raise ValueError("Unit not found — register the unit first")
    if unit["status"] not in ("available", "hold"):
        raise ValueError(f"Unit is not available for booking (status: {unit['status']})")

    if data.get("customer"):
        raise ValueError("Register the customer first, then select them on the booking form")
    customer_id = data.get("customer_id")
    if not customer_id:
        raise ValueError("Select an existing customer")
    customer = fetch_one(conn, "SELECT id FROM customers WHERE id=?", (customer_id,))
    if not customer:
        raise ValueError("Customer not found — register the customer first")

    project_id = data.get("project_id") or unit["project_id"]
    if project_id != unit["project_id"]:
        raise ValueError("Selected unit does not belong to the selected project")
    if not fetch_one(conn, "SELECT id FROM projects WHERE id=?", (project_id,)):
        raise ValueError("Project not found")

    agent_id = data.get("agent_id") or _resolve_agent_id(conn, data.get("agent"))
    booking_no = data.get("booking_no") or _next_booking_no(conn)
    sale_price = data["sale_price"]
    booking_amount = data.get("booking_amount") or data.get("down_payment") or 0

    cur = conn.execute(
        """INSERT INTO bookings(booking_no, customer_id, unit_id, project_id, agent_id,
           booking_date, base_sale_price, final_sale_price, booking_amount,
           possession_date, status, payment_mode, notes)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            booking_no, customer_id, data["unit_id"], project_id, agent_id,
            data.get("booking_date") or date.today().isoformat(),
            data.get("base_sale_price") or sale_price, sale_price, booking_amount,
            data.get("possession_date"), "active",
            data.get("payment_mode", "Cheque"), data.get("notes"),
        ),
    )
    booking_id = cur.lastrowid

    conn.execute(
        "UPDATE units SET status='booked', final_sold_price=? WHERE id=?",
        (sale_price, data["unit_id"]),
    )

    installments = data.get("installments") or []
    for n, inst in enumerate(installments, 1):
        amt = inst["amount"]
        conn.execute(
            """INSERT INTO installments(booking_id, customer_id, unit_id, installment_no,
               due_date, amount, paid_amount, remaining_amount, type, notes, status)
               VALUES(?,?,?,?,?,?,0,?,?,?,?)""",
            (
                booking_id, customer_id, data["unit_id"], n,
                inst["due_date"], amt, amt, inst.get("type", "Monthly"),
                inst.get("notes", ""), "pending",
            ),
        )

    if agent_id:
        rate = settings_svc.get_float(conn, "default_agent_commission_pct", 2.0)
        ag = fetch_one(conn, "SELECT default_rate_pct FROM agents WHERE id=?", (agent_id,))
        if ag and ag["default_rate_pct"]:
            rate = ag["default_rate_pct"]
        commission = int(sale_price * rate / 100)
        conn.execute(
            """INSERT INTO agent_commissions(booking_id, agent_id, rate_pct,
               commission_amount, paid_amount, status) VALUES(?,?,?,?,0,'earned')""",
            (booking_id, agent_id, rate, commission),
        )

    audit_svc.log(conn, "booking", booking_id, "created", {"booking_no": booking_no, "unit_id": data["unit_id"]})
    inst_svc.refresh_statuses(conn, booking_id)

    return fetch_one(conn, "SELECT * FROM bookings WHERE id=?", (booking_id,))


def cancel_booking(conn, booking_id: int, reason: str | None = None) -> dict:
    booking = fetch_one(conn, "SELECT * FROM bookings WHERE id=? AND status='active'", (booking_id,))
    if not booking:
        raise ValueError("Active booking not found")

    paid_row = fetch_one(
        conn, "SELECT COALESCE(SUM(amount),0) AS total FROM payments WHERE booking_id=?",
        (booking_id,),
    )
    total_paid = paid_row["total"] if paid_row else 0
    forfeit_pct = settings_svc.get_float(conn, "cancellation_forfeit_pct", 30.0)
    forfeit = int(booking["booking_amount"] * forfeit_pct / 100)
    refund = max(total_paid - forfeit, 0)

    conn.execute("UPDATE bookings SET status='cancelled' WHERE id=?", (booking_id,))
    conn.execute(
        """UPDATE installments SET status='cancelled', remaining_amount=0
           WHERE booking_id=? AND status NOT IN ('paid')""",
        (booking_id,),
    )
    conn.execute(
        "UPDATE units SET status='available', hold_customer_id=NULL, hold_until=NULL WHERE id=?",
        (booking["unit_id"],),
    )
    conn.execute(
        """INSERT INTO booking_cancellations(booking_id, reason, total_paid,
           forfeit_amount, refund_amount, forfeit_pct) VALUES(?,?,?,?,?,?)""",
        (booking_id, reason, total_paid, forfeit, refund, forfeit_pct),
    )

    comm = fetch_one(conn, "SELECT id FROM agent_commissions WHERE booking_id=?", (booking_id,))
    if comm:
        conn.execute(
            "UPDATE agent_commissions SET status='reversed' WHERE booking_id=?",
            (booking_id,),
        )

    audit_svc.log(conn, "booking", booking_id, "cancelled", {
        "forfeit": forfeit, "refund": refund, "reason": reason,
    })
    return {
        "ok": True,
        "booking_id": booking_id,
        "total_paid": total_paid,
        "forfeit_amount": forfeit,
        "refund_amount": refund,
        "forfeit_pct": forfeit_pct,
    }


def preview_cancel(conn, booking_id: int) -> dict:
    booking = fetch_one(conn, "SELECT * FROM bookings WHERE id=? AND status='active'", (booking_id,))
    if not booking:
        raise ValueError("Active booking not found")
    paid_row = fetch_one(
        conn, "SELECT COALESCE(SUM(amount),0) AS total FROM payments WHERE booking_id=?",
        (booking_id,),
    )
    total_paid = paid_row["total"] if paid_row else 0
    forfeit_pct = settings_svc.get_float(conn, "cancellation_forfeit_pct", 30.0)
    forfeit = int(booking["booking_amount"] * forfeit_pct / 100)
    return {
        "booking_id": booking_id,
        "booking_no": booking["booking_no"],
        "unit_id": booking["unit_id"],
        "total_paid": total_paid,
        "forfeit_pct": forfeit_pct,
        "forfeit_amount": forfeit,
        "refund_amount": max(total_paid - forfeit, 0),
    }


def transfer_booking(conn, booking_id: int, new_customer_id: int, notes: str | None = None,
                    transfer_date: str | None = None) -> dict:
    booking = fetch_one(conn, "SELECT * FROM bookings WHERE id=? AND status='active'", (booking_id,))
    if not booking:
        raise ValueError("Active booking not found")
    if int(new_customer_id) == int(booking["customer_id"]):
        raise ValueError("Choose a different customer")
    new_c = fetch_one(conn, "SELECT id, name FROM customers WHERE id=?", (new_customer_id,))
    if not new_c:
        raise ValueError("Customer not found")
    from_id = booking["customer_id"]
    when = (transfer_date or "").strip() or date.today().isoformat()
    conn.execute("UPDATE bookings SET customer_id=? WHERE id=?", (new_customer_id, booking_id))
    conn.execute("UPDATE installments SET customer_id=? WHERE booking_id=?", (new_customer_id, booking_id))
    conn.execute("UPDATE payments SET customer_id=? WHERE booking_id=?", (new_customer_id, booking_id))
    conn.execute(
        """INSERT INTO booking_transfers(booking_id, from_customer_id, to_customer_id, transfer_date, notes)
           VALUES(?,?,?,?,?)""",
        (booking_id, from_id, new_customer_id, when, (notes or "").strip() or None),
    )
    audit_svc.log(conn, "booking", booking_id, "transferred", {
        "from_customer_id": from_id, "to_customer_id": new_customer_id,
    })
    return fetch_one(conn, "SELECT * FROM bookings WHERE id=?", (booking_id,))


def list_bookings(conn, project_id: int | None = None) -> list[dict]:
    q = """SELECT b.*, c.name AS customer_name, u.unit_no, p.name AS project_name
           FROM bookings b
           JOIN customers c ON c.id=b.customer_id
           JOIN units u ON u.id=b.unit_id
           JOIN projects p ON p.id=b.project_id WHERE 1=1"""
    params: list = []
    if project_id:
        q += " AND b.project_id=?"
        params.append(project_id)
    q += " ORDER BY b.booking_date DESC"
    return fetch_all(conn, q, tuple(params))
