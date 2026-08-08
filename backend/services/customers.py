from backend.database import fetch_all, fetch_one
from backend.services import installments as inst_svc


def _customer_status(conn, customer_id: int) -> str | None:
    inst_svc.refresh_statuses(conn)
    row = fetch_one(
        conn,
        """SELECT
             SUM(CASE WHEN status='overdue' THEN 1 ELSE 0 END) AS ov,
             SUM(CASE WHEN status IN ('pending','partial') THEN 1 ELSE 0 END) AS pe
           FROM installments WHERE customer_id=?""",
        (customer_id,),
    )
    if not row:
        return None
    if (row["ov"] or 0) > 0:
        return "Overdue"
    if (row["pe"] or 0) > 0:
        return "On Track"
    bookings = fetch_one(
        conn, "SELECT COUNT(*) AS n FROM bookings WHERE customer_id=? AND status='active'",
        (customer_id,),
    )
    return "Cleared" if bookings and bookings["n"] > 0 else None


def _clean(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_customer_data(data: dict) -> dict:
    name = _clean(data.get("name"))
    cnic = _clean(data.get("cnic"))
    if not name or not cnic:
        raise ValueError("Name and CNIC are required")
    return {
        "name": name,
        "cnic": cnic,
        "father_name": _clean(data.get("father_name")),
        "description": _clean(data.get("description")),
        "address": _clean(data.get("address") or data.get("residential_address")),
        "phone": _clean(data.get("phone") or data.get("contact_number")),
        "emergency_contact_number": _clean(data.get("emergency_contact_number")),
        "email": _clean(data.get("email")),
    }


def enrich_customer(conn, customer: dict) -> dict:
    cid = customer["id"]
    units = fetch_all(
        conn,
        """SELECT u.unit_no, b.id AS booking_id, b.final_sale_price AS sale_price
           FROM bookings b JOIN units u ON u.id=b.unit_id
           WHERE b.customer_id=? AND b.status='active'""",
        (cid,),
    )
    customer["units"] = ", ".join(u["unit_no"] for u in units) if units else None
    customer["total_value"] = sum(u["sale_price"] or 0 for u in units) if units else 0
    customer["phone"] = customer.get("contact_number")
    customer["address"] = customer.get("residential_address")

    paid = fetch_one(
        conn,
        "SELECT COALESCE(SUM(amount),0) AS v, MAX(payment_date) AS last FROM payments WHERE customer_id=?",
        (cid,),
    )
    customer["total_paid"] = paid["v"] if paid else 0
    customer["last_payment"] = paid["last"] if paid else None
    customer["outstanding"] = (customer["total_value"] or 0) - (customer["total_paid"] or 0)
    customer["cust_status"] = _customer_status(conn, cid)
    return customer


def list_customers(conn) -> list[dict]:
    customers = fetch_all(conn, "SELECT * FROM customers ORDER BY name")
    return [enrich_customer(conn, c) for c in customers]


def get_customer(conn, customer_id: int) -> dict | None:
    c = fetch_one(conn, "SELECT * FROM customers WHERE id=?", (customer_id,))
    if not c:
        return None
    enriched = enrich_customer(conn, c)
    enriched["bookings"] = fetch_all(
        conn,
        """SELECT b.*, u.unit_no, p.name AS project_name
           FROM bookings b
           JOIN units u ON u.id=b.unit_id
           JOIN projects p ON p.id=b.project_id
           WHERE b.customer_id=?
           ORDER BY b.booking_date DESC""",
        (customer_id,),
    )
    enriched["payments"] = fetch_all(
        conn,
        """SELECT p.*, r.receipt_no, u.unit_no
           FROM payments p
           LEFT JOIN receipts r ON r.payment_id=p.id
           LEFT JOIN bookings bk ON bk.id=p.booking_id
           LEFT JOIN units u ON u.id=bk.unit_id
           WHERE p.customer_id=?
           ORDER BY p.payment_date DESC""",
        (customer_id,),
    )
    return enriched


def create_customer(conn, data: dict) -> dict:
    payload = normalize_customer_data(data)
    if fetch_one(conn, "SELECT id FROM customers WHERE cnic=?", (payload["cnic"],)):
        raise ValueError("CNIC already exists")
    cur = conn.execute(
        """INSERT INTO customers(name, father_name, description, residential_address,
           cnic, contact_number, emergency_contact_number, email)
           VALUES(?,?,?,?,?,?,?,?)""",
        (
            payload["name"], payload["father_name"], payload["description"],
            payload["address"], payload["cnic"], payload["phone"],
            payload["emergency_contact_number"], payload["email"],
        ),
    )
    return enrich_customer(conn, fetch_one(conn, "SELECT * FROM customers WHERE id=?", (cur.lastrowid,)))


def update_customer(conn, customer_id: int, data: dict) -> dict | None:
    if not fetch_one(conn, "SELECT id FROM customers WHERE id=?", (customer_id,)):
        return None
    payload = normalize_customer_data(data)
    dup = fetch_one(
        conn, "SELECT id FROM customers WHERE cnic=? AND id!=?",
        (payload["cnic"], customer_id),
    )
    if dup:
        raise ValueError("CNIC already exists")
    conn.execute(
        """UPDATE customers SET name=?, father_name=?, description=?, residential_address=?,
           cnic=?, contact_number=?, emergency_contact_number=?, email=?
           WHERE id=?""",
        (
            payload["name"], payload["father_name"], payload["description"],
            payload["address"], payload["cnic"], payload["phone"],
            payload["emergency_contact_number"], payload["email"], customer_id,
        ),
    )
    return enrich_customer(conn, fetch_one(conn, "SELECT * FROM customers WHERE id=?", (customer_id,)))


def delete_customer(conn, customer_id: int) -> None:
    if not fetch_one(conn, "SELECT id FROM customers WHERE id=?", (customer_id,)):
        raise ValueError("Customer not found")
    hold = fetch_one(
        conn, "SELECT unit_no FROM units WHERE hold_customer_id=? LIMIT 1",
        (customer_id,),
    )
    if hold:
        raise ValueError(f"Cannot delete: customer is holding unit {hold['unit_no']}")
    if fetch_one(conn, "SELECT id FROM bookings WHERE customer_id=? LIMIT 1", (customer_id,)):
        raise ValueError("Cannot delete a customer with bookings")
    if fetch_one(conn, "SELECT id FROM payments WHERE customer_id=? LIMIT 1", (customer_id,)):
        raise ValueError("Cannot delete a customer with payment history")
    conn.execute("DELETE FROM customers WHERE id=?", (customer_id,))
