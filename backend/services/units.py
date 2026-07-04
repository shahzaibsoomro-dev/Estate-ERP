import json

from backend.database import fetch_all, fetch_one
from backend.services import installments as inst_svc
from backend.services.project_filter import sql_in


def _parse_unit_attributes(attrs) -> list:
    if isinstance(attrs, str):
        try:
            parsed = json.loads(attrs)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return attrs if isinstance(attrs, list) else []


def _map_unit(row: dict) -> dict:
    u = dict(row)
    raw_status = u.get("status", "available")
    u["raw_status"] = raw_status
    if raw_status in ("booked", "sold", "possession_delivered"):
        u["status"] = "sold"
    u["floor"] = u.get("floor_number")
    u["type"] = u.get("unit_type")
    ghaz = u.get("area_ghaz")
    u["size_sqft"] = int((ghaz or 0) * 9) if ghaz else None
    u["price"] = u.get("base_sale_price")
    parsed_attrs = _parse_unit_attributes(u.get("unit_attributes"))
    u["unit_attributes"] = parsed_attrs
    u["facing"] = parsed_attrs[0] if parsed_attrs else ""
    return u


def list_units(conn, project_id: int | None = None, project_ids: list[int] | None = None,
               status: str | None = None, floor: int | None = None) -> list[dict]:
    q = """SELECT u.*, p.name AS project_name FROM units u
           JOIN projects p ON p.id=u.project_id WHERE 1=1"""
    params: list = []
    ids = project_ids if project_ids else ([project_id] if project_id else None)
    filt, filt_params = sql_in("u.project_id", ids)
    q += filt
    params.extend(filt_params)
    if status:
        q += " AND u.status=?"
        params.append(status)
    if floor is not None:
        q += " AND u.floor_number=?"
        params.append(floor)
    q += " ORDER BY u.floor_number, u.id"
    return [_map_unit(r) for r in fetch_all(conn, q, tuple(params))]


def get_unit(conn, unit_id: int) -> dict | None:
    row = fetch_one(
        conn,
        """SELECT u.*, p.name AS project_name, p.location FROM units u
           JOIN projects p ON p.id=u.project_id WHERE u.id=?""",
        (unit_id,),
    )
    return _map_unit(row) if row else None


def get_unit_detail(conn, unit_id: int) -> dict | None:
    unit = get_unit(conn, unit_id)
    if not unit:
        return None

    booking = fetch_one(
        conn,
        """SELECT b.*, c.name AS customer_name, c.cnic, c.contact_number AS phone,
           c.email, c.residential_address AS address, c.father_name AS nok_name
           FROM bookings b
           JOIN customers c ON c.id=b.customer_id
           WHERE b.unit_id=? AND b.status='active'
           ORDER BY b.id DESC LIMIT 1""",
        (unit_id,),
    )
    if booking and booking.get("agent_id"):
        ag = fetch_one(conn, "SELECT name FROM agents WHERE id=?", (booking["agent_id"],))
        booking["agent"] = ag["name"] if ag else "None"
    elif booking:
        booking["agent"] = "None"

    installments = []
    payments = []
    if booking:
        installments = inst_svc.list_for_booking(conn, booking["id"])
        payments = fetch_all(
            conn,
            """SELECT py.*, i.type AS inst_type, i.due_date, r.receipt_no FROM payments py
               LEFT JOIN installments i ON i.id=py.installment_id
               LEFT JOIN receipts r ON r.payment_id=py.id
               WHERE py.booking_id=? ORDER BY py.payment_date DESC""",
            (booking["id"],),
        )
        for p in payments:
            p["paid_date"] = p["payment_date"]
            p["method"] = p["payment_method"]

    total_paid = sum(p["amount"] for p in payments)
    sale_price = booking["final_sale_price"] if booking else 0
    outstanding = max(sale_price - total_paid, 0) if booking else 0
    pct = round(total_paid / sale_price * 100) if booking and sale_price else 0

    return {
        "unit": unit,
        "booking": booking,
        "installments": installments,
        "payments": payments,
        "summary": {
            "sale_price": sale_price,
            "total_paid": total_paid,
            "outstanding": outstanding,
            "pct_paid": pct,
        },
    }


def create_unit(conn, data: dict) -> dict:
    import json
    dup = fetch_one(
        conn, "SELECT id FROM units WHERE project_id=? AND unit_no=?",
        (data["project_id"], data["unit_no"]),
    )
    if dup:
        raise ValueError("Unit number already exists in this project")
    cur = conn.execute(
        """INSERT INTO units(project_id, unit_no, description, unit_type, residential_type,
           floor_number, area_ghaz, block_tower, bedrooms, bathrooms, status,
           base_sale_price, final_sold_price, booking_amount_required, furnishing_status,
           unit_attributes, additional_requirements, possession_date)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            data["project_id"], data["unit_no"], data.get("description"),
            data.get("unit_type", "Flat"), data.get("residential_type"),
            data.get("floor_number", 1), data.get("area_ghaz"),
            data.get("block_tower"), data.get("bedrooms"), data.get("bathrooms"),
            data.get("status", "available"), data.get("base_sale_price"),
            data.get("final_sold_price"), data.get("booking_amount_required"),
            data.get("furnishing_status"), json.dumps(data.get("unit_attributes") or []),
            data.get("additional_requirements"), data.get("possession_date"),
        ),
    )
    return get_unit(conn, cur.lastrowid)


def update_status(conn, unit_id: int, status: str, hold_customer_id: int | None = None,
                  hold_until: str | None = None, hold_notes: str | None = None) -> dict | None:
    unit = fetch_one(conn, "SELECT id FROM units WHERE id=?", (unit_id,))
    if not unit:
        return None
    conn.execute(
        """UPDATE units SET status=?, hold_customer_id=?, hold_until=?, hold_notes=?
           WHERE id=?""",
        (status, hold_customer_id, hold_until, hold_notes, unit_id),
    )
    return get_unit(conn, unit_id)


def update_unit(conn, unit_id: int, data: dict) -> dict:
    import json
    unit = fetch_one(conn, "SELECT * FROM units WHERE id=?", (unit_id,))
    if not unit:
        raise ValueError("Unit not found")
    if fetch_one(conn, "SELECT id FROM bookings WHERE unit_id=? AND status='active'", (unit_id,)):
        raise ValueError("Cannot edit unit with an active booking — cancel booking first")
    if unit["status"] in ("sold", "booked", "possession_delivered"):
        raise ValueError("Cannot edit a sold or booked unit")

    new_no = data.get("unit_no", unit["unit_no"])
    if new_no != unit["unit_no"]:
        dup = fetch_one(
            conn, "SELECT id FROM units WHERE project_id=? AND unit_no=? AND id!=?",
            (unit["project_id"], new_no, unit_id),
        )
        if dup:
            raise ValueError("Unit number already exists in this project")

    conn.execute(
        """UPDATE units SET unit_no=?, description=?, unit_type=?, residential_type=?,
           floor_number=?, area_ghaz=?, block_tower=?, bedrooms=?, bathrooms=?,
           base_sale_price=?, booking_amount_required=?, furnishing_status=?,
           unit_attributes=?, additional_requirements=?, possession_date=?
           WHERE id=?""",
        (
            new_no, data.get("description"), data.get("unit_type", unit["unit_type"]),
            data.get("residential_type"), data.get("floor_number", unit["floor_number"]),
            data.get("area_ghaz"), data.get("block_tower"), data.get("bedrooms"),
            data.get("bathrooms"), data.get("base_sale_price"),
            data.get("booking_amount_required"), data.get("furnishing_status"),
            json.dumps(data.get("unit_attributes") or []),
            data.get("additional_requirements"), data.get("possession_date"),
            unit_id,
        ),
    )
    return get_unit(conn, unit_id)


def delete_unit(conn, unit_id: int) -> None:
    unit = fetch_one(conn, "SELECT id, status FROM units WHERE id=?", (unit_id,))
    if not unit:
        raise ValueError("Unit not found")
    if fetch_one(conn, "SELECT id FROM bookings WHERE unit_id=? LIMIT 1", (unit_id,)):
        raise ValueError("Cannot delete a unit that has booking history")
    if unit["status"] in ("sold", "booked", "possession_delivered"):
        raise ValueError("Cannot delete sold or booked units — cancel booking first")
    conn.execute("DELETE FROM units WHERE id=?", (unit_id,))
