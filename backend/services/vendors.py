from backend.database import fetch_all, fetch_one


def list_vendors(conn) -> list[dict]:
    vendors = fetch_all(conn, "SELECT * FROM vendors ORDER BY name")
    for v in vendors:
        _attach_balances(conn, v)
    return vendors


def _attach_balances(conn, vendor: dict) -> dict:
    pos = fetch_one(
        conn,
        """SELECT COALESCE(SUM(total),0) AS total_payable,
                  COALESCE(SUM(CASE WHEN status='closed' THEN total ELSE 0 END),0) AS closed_total
           FROM purchase_orders WHERE vendor_id=?""",
        (vendor["id"],),
    )
    paid = fetch_one(
        conn,
        "SELECT COALESCE(SUM(amount),0) AS v FROM vendor_payments WHERE vendor_id=?",
        (vendor["id"],),
    )
    vendor["total_payable"] = pos["total_payable"] if pos else 0
    vendor["total_paid"] = paid["v"] if paid else 0
    vendor["balance"] = vendor["total_payable"] - vendor["total_paid"]
    return vendor


def create_vendor(conn, data: dict) -> dict:
    cur = conn.execute(
        "INSERT INTO vendors(name, description, contact, category, status) VALUES(?,?,?,?,?)",
        (
            data["name"], data.get("description"), data.get("contact"),
            data.get("category"), data.get("status", "active"),
        ),
    )
    v = fetch_one(conn, "SELECT * FROM vendors WHERE id=?", (cur.lastrowid,))
    return _attach_balances(conn, v)


def list_purchase_orders(conn) -> list[dict]:
    rows = fetch_all(
        conn,
        """SELECT po.*, v.name AS vendor_name, p.name AS project_name
           FROM purchase_orders po
           JOIN vendors v ON v.id=po.vendor_id
           JOIN projects p ON p.id=po.project_id
           ORDER BY po.order_date DESC""",
    )
    for r in rows:
        paid = fetch_one(
            conn,
            "SELECT COALESCE(SUM(amount),0) AS v FROM vendor_payments WHERE purchase_order_id=?",
            (r["id"],),
        )
        _map_po_status(r, paid["v"] if paid else 0)
    return rows


def _map_po_status(po: dict, paid: int = 0) -> dict:
    """Map internal status to legacy frontend values."""
    status = po.get("status", "ordered")
    grn = po.get("grn_status", "pending")
    if status == "closed":
        po["status"] = "completed"
    elif status == "delivered" or grn == "done":
        po["status"] = "completed" if paid >= po["total"] else "payment_pending"
        po["grn_status"] = "done"
    elif grn == "na":
        po["status"] = "draft"
    else:
        po["status"] = "approved"
    return po


def create_purchase_order(conn, data: dict) -> dict:
    cur = conn.execute(
        """INSERT INTO purchase_orders(po_no, vendor_id, project_id, budget_category_id,
           category, material, quantity, unit_cost, total, order_date,
           expected_delivery_date, status, grn_status, site, notes)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            data["po_no"], data["vendor_id"], data["project_id"],
            data.get("budget_category_id"), data.get("category"), data["material"],
            data.get("qty") or data.get("quantity"), data.get("unit_cost"), data["total"],
            data.get("order_date"), data.get("expected_delivery_date"),
            data.get("status", "ordered"), data.get("grn_status", "pending"),
            data.get("site"), data.get("notes"),
        ),
    )
    return fetch_one(conn, "SELECT * FROM purchase_orders WHERE id=?", (cur.lastrowid,))


def update_po_status(conn, po_id: int, status: str) -> dict | None:
    po = fetch_one(conn, "SELECT * FROM purchase_orders WHERE id=?", (po_id,))
    if not po:
        return None
    legacy = status
    grn = po["grn_status"]
    if status == "approved":
        conn.execute("UPDATE purchase_orders SET status='ordered' WHERE id=?", (po_id,))
    elif status == "completed":
        conn.execute(
            "UPDATE purchase_orders SET status='closed', grn_status='done' WHERE id=?",
            (po_id,),
        )
    elif status == "payment_pending":
        conn.execute(
            "UPDATE purchase_orders SET status='delivered', grn_status='done' WHERE id=?",
            (po_id,),
        )
    else:
        conn.execute("UPDATE purchase_orders SET status=? WHERE id=?", (legacy, po_id))
    return fetch_one(conn, "SELECT * FROM purchase_orders WHERE id=?", (po_id,))


def record_vendor_payment(conn, data: dict) -> dict:
    cur = conn.execute(
        """INSERT INTO vendor_payments(vendor_id, purchase_order_id, amount,
           payment_date, payment_method, reference_number, notes)
           VALUES(?,?,?,?,?,?,?)""",
        (
            data["vendor_id"], data.get("purchase_order_id"), data["amount"],
            data["payment_date"], data.get("payment_method", "Bank Transfer"),
            data.get("reference_number"), data.get("notes"),
        ),
    )
    po_id = data.get("purchase_order_id")
    if po_id:
        po = fetch_one(conn, "SELECT total FROM purchase_orders WHERE id=?", (po_id,))
        paid = fetch_one(
            conn,
            "SELECT COALESCE(SUM(amount),0) AS v FROM vendor_payments WHERE purchase_order_id=?",
            (po_id,),
        )
        if po and paid and paid["v"] >= po["total"]:
            conn.execute(
                "UPDATE purchase_orders SET status='closed' WHERE id=?", (po_id,),
            )
    return {"ok": True, "id": cur.lastrowid}
