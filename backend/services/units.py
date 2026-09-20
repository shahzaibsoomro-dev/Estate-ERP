import json

from datetime import date

from backend.database import fetch_all, fetch_one
from backend.services import audit as audit_svc
from backend.services import installments as inst_svc
from backend.services.project_filter import sql_in

UNIT_TYPES = ("residential", "commercial")
TYPE_ALIASES = {
    "shop": "commercial", "office": "commercial", "showroom": "commercial",
    "warehouse": "commercial", "commercial": "commercial",
    "flat": "residential", "house": "residential", "apartment": "residential",
    "penthouse": "residential", "residential": "residential",
}


def normalize_unit_type(raw) -> str:
    key = (raw or "residential").strip().lower()
    if key in UNIT_TYPES:
        return key
    if key in TYPE_ALIASES:
        return TYPE_ALIASES[key]
    raise ValueError("Unit type must be residential or commercial")


def type_label(unit_type: str | None) -> str:
    return "Commercial" if (unit_type or "") == "commercial" else "Residential"


def _parse_unit_attributes(attrs) -> list:
    if isinstance(attrs, str):
        try:
            parsed = json.loads(attrs)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return attrs if isinstance(attrs, list) else []


def display_unit_status(raw_status: str | None) -> str:
    raw = (raw_status or "available").lower()
    if raw == "possession_delivered":
        return "delivered"
    if raw in ("sold", "booked"):
        return "booked"
    if raw == "hold":
        return "hold"
    return "available"


def _map_unit(row: dict) -> dict:
    u = dict(row)
    raw_status = u.get("status", "available")
    u["raw_status"] = raw_status
    u["status"] = display_unit_status(raw_status)
    u["floor"] = u.get("floor_number")
    try:
        u["unit_type"] = normalize_unit_type(u.get("unit_type"))
    except ValueError:
        u["unit_type"] = "residential"
    u["type"] = u["unit_type"]
    u["type_label"] = type_label(u["unit_type"])
    ghaz = u.get("area_ghaz")
    u["size_sqft"] = int((ghaz or 0) * 9) if ghaz else None
    u["price"] = u.get("base_sale_price")
    parsed_attrs = _parse_unit_attributes(u.get("unit_attributes"))
    u["unit_attributes"] = parsed_attrs
    u["facing"] = parsed_attrs[0] if parsed_attrs else ""
    return u


def list_units(conn, project_id: int | None = None, project_ids: list[int] | None = None,
               status: str | None = None, floor: int | None = None) -> list[dict]:
    from backend.services import holds as holds_svc
    holds_svc.expire_due_holds(conn)
    q = """SELECT u.*, p.name AS project_name FROM units u
           JOIN projects p ON p.id=u.project_id WHERE 1=1"""
    params: list = []
    ids = project_ids if project_ids else ([project_id] if project_id else None)
    filt, filt_params = sql_in("u.project_id", ids)
    q += filt
    params.extend(filt_params)
    if status:
        if status == "delivered":
            q += " AND u.status='possession_delivered'"
        elif status == "booked":
            q += " AND u.status IN ('booked','sold')"
        else:
            q += " AND u.status=?"
            params.append(status)
    if floor is not None:
        q += " AND u.floor_number=?"
        params.append(floor)
    q += " ORDER BY u.floor_number, u.id"
    units = [_map_unit(r) for r in fetch_all(conn, q, tuple(params))]
    for u in units:
        if u.get("raw_status") == "hold" and not u.get("hold_customer_id"):
            h = fetch_one(
                conn,
                """SELECT customer_id, hold_until, notes, token_amount, id
                   FROM unit_holds WHERE unit_id=? AND status='active'
                   ORDER BY id DESC LIMIT 1""",
                (u["id"],),
            )
            if h:
                u["hold_customer_id"] = h["customer_id"]
                u["hold_until"] = h["hold_until"]
                u["hold_notes"] = h["notes"]
                u["hold_token_amount"] = h["token_amount"]
                u["hold_id"] = h["id"]
    return units


def get_unit(conn, unit_id: int) -> dict | None:
    row = fetch_one(
        conn,
        """SELECT u.*, p.name AS project_name, p.location FROM units u
           JOIN projects p ON p.id=u.project_id WHERE u.id=?""",
        (unit_id,),
    )
    return _map_unit(row) if row else None


def get_unit_detail(conn, unit_id: int) -> dict | None:
    from backend.services import holds as holds_svc

    holds_svc.expire_due_holds(conn, unit_id=unit_id)
    unit = get_unit(conn, unit_id)
    if not unit:
        return None

    booking = fetch_one(
        conn,
        """SELECT b.*, c.name AS customer_name, c.cnic, c.contact_number AS phone,
           c.email, c.residential_address AS address,
           c.nok_name, c.nok_relationship, c.nok_phone, c.nok_cnic, c.nok_address,
           c.father_name
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
            """SELECT py.*, i.type AS inst_type, i.due_date, r.receipt_no,
                      CASE WHEN hta.id IS NOT NULL THEN 1 ELSE 0 END AS from_hold_token
               FROM payments py
               LEFT JOIN installments i ON i.id=py.installment_id
               LEFT JOIN receipts r ON r.payment_id=py.id
               LEFT JOIN hold_token_applications hta ON hta.payment_id=py.id
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

    active_hold = holds_svc.get_active_hold(conn, unit_id)
    hold_info = None
    if active_hold:
        detail = holds_svc.hold_detail(conn, active_hold["id"])
        hold_info = detail
        # Mirror legacy fields on unit for UI
        unit["hold_customer_id"] = active_hold.get("customer_id")
        unit["hold_until"] = active_hold.get("hold_until")
        unit["hold_notes"] = active_hold.get("notes")
        unit["hold_token_amount"] = active_hold.get("token_amount")
        unit["hold_id"] = active_hold.get("id")
        if detail.get("receipt"):
            unit["hold_receipt_no"] = detail["receipt"].get("receipt_no")

    return {
        "unit": unit,
        "booking": booking,
        "installments": installments,
        "payments": payments,
        "hold": hold_info,
        "hold_history": holds_svc.hold_history(conn, unit_id),
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
    if (data.get("status") or "available").lower() not in ("available", "blocked"):
        raise ValueError("New units start as available — use a hold or booking to change that")
    if data.get("base_sale_price") is not None and int(data["base_sale_price"]) < 0:
        raise ValueError("Price cannot be negative")
    unit_type = normalize_unit_type(data.get("unit_type"))
    layout = data.get("residential_type") if unit_type == "residential" else None
    cur = conn.execute(
        """INSERT INTO units(project_id, unit_no, description, unit_type, residential_type,
           floor_number, area_ghaz, block_tower, bedrooms, bathrooms, status,
           base_sale_price, final_sold_price, booking_amount_required, furnishing_status,
           unit_attributes, additional_requirements, possession_date)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            data["project_id"], data["unit_no"], data.get("description"),
            unit_type, layout,
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
                  hold_until: str | None = None, hold_notes: str | None = None,
                  token_amount: int = 0, **extra) -> dict | None:
    from backend.services import holds as holds_svc

    unit = fetch_one(conn, "SELECT * FROM units WHERE id=?", (unit_id,))
    if not unit:
        return None
    status = (status or "").lower()
    if status == "hold":
        holds_svc.create_hold(conn, unit_id, {
            "customer_id": hold_customer_id,
            "hold_until": hold_until,
            "notes": hold_notes,
            "token_amount": token_amount,
            **extra,
        })
        return get_unit(conn, unit_id)
    allowed = {"available", "hold", "booked", "sold", "possession_delivered", "blocked"}
    if status not in allowed:
        raise ValueError(f"Unknown unit status '{status}'")
    has_booking = fetch_one(conn, "SELECT id FROM bookings WHERE unit_id=? AND status='active'", (unit_id,))
    if status in ("booked", "sold", "possession_delivered") and not has_booking:
        raise ValueError("A unit becomes booked or sold only through a booking — create the booking instead")
    if status in ("available", "blocked") and has_booking:
        raise ValueError("This unit has an active booking — cancel the booking first")
    if status == "available" and unit["status"] == "hold":
        active = holds_svc.get_active_hold(conn, unit_id)
        if active:
            holds_svc.release_hold(conn, active["id"], hold_notes or "Hold released")
            return get_unit(conn, unit_id)
    conn.execute(
        """UPDATE units SET status=?, hold_customer_id=?, hold_until=?, hold_notes=?
           WHERE id=?""",
        (status, hold_customer_id, hold_until, hold_notes, unit_id),
    )
    audit_svc.log(conn, "unit", unit_id, "status", {"status": status})
    return get_unit(conn, unit_id)


def mark_possession(conn, unit_id: int, possession_date: str | None = None,
                    checklist_responses: list[dict] | None = None,
                    completed_by: str | None = None,
                    skip_checklist: bool = False,
                    complete_all: bool = False) -> dict:
    unit = fetch_one(conn, "SELECT * FROM units WHERE id=?", (unit_id,))
    if not unit:
        raise ValueError("Unit not found")
    booking = fetch_one(
        conn,
        "SELECT * FROM bookings WHERE unit_id=? AND status='active' ORDER BY id DESC LIMIT 1",
        (unit_id,),
    )
    if not booking:
        raise ValueError("Active booking required for possession")
    when = (possession_date or "").strip() or date.today().isoformat()

    checklist = None
    if not skip_checklist:
        from backend.services import possession as poss_svc
        checklist = poss_svc.start_checklist(conn, unit_id, when, completed_by=completed_by)
        responses = list(checklist_responses or [])
        if complete_all and not responses:
            responses = [
                {"id": r["id"], "checked": True}
                for r in (checklist.get("responses") or [])
            ]
        if responses:
            checklist = poss_svc.update_responses(
                conn, checklist["id"], responses, completed_by=completed_by,
            )
        missing = [
            r["label"] for r in (checklist.get("responses") or [])
            if r.get("is_required") and not r.get("checked")
        ]
        if missing:
            raise ValueError(
                "Complete possession checklist first: " + ", ".join(missing[:4])
                + ("…" if len(missing) > 4 else "")
            )
        poss_svc.complete_checklist(conn, checklist["id"], completed_by=completed_by)

    conn.execute(
        """UPDATE units SET status='possession_delivered', possession_date=? WHERE id=?""",
        (when, unit_id),
    )
    conn.execute("UPDATE bookings SET possession_date=? WHERE id=?", (when, booking["id"]))
    audit_svc.log(conn, "unit", unit_id, "possession", {
        "booking_id": booking["id"], "possession_date": when,
        "checklist_id": checklist["id"] if checklist else None,
    })
    detail = get_unit_detail(conn, unit_id)
    if checklist:
        detail["possession_checklist"] = checklist
    return detail


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

    unit_type = normalize_unit_type(data.get("unit_type") or unit["unit_type"])
    conn.execute(
        """UPDATE units SET unit_no=?, description=?, unit_type=?, residential_type=?,
           floor_number=?, area_ghaz=?, block_tower=?, bedrooms=?, bathrooms=?,
           base_sale_price=?, booking_amount_required=?, furnishing_status=?,
           unit_attributes=?, additional_requirements=?, possession_date=?
           WHERE id=?""",
        (
            new_no, data.get("description"), unit_type,
            data.get("residential_type") if unit_type == "residential" else None,
            data.get("floor_number", unit["floor_number"]),
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
    if unit["status"] == "hold" or fetch_one(
        conn, "SELECT id FROM unit_holds WHERE unit_id=? AND status='active' LIMIT 1", (unit_id,),
    ):
        raise ValueError("Cannot delete a unit on hold — release the hold first")
    hold_ids = [
        r["id"] for r in fetch_all(conn, "SELECT id FROM unit_holds WHERE unit_id=?", (unit_id,))
    ]
    for hid in hold_ids:
        conn.execute("DELETE FROM hold_token_applications WHERE hold_id=?", (hid,))
        conn.execute("DELETE FROM hold_receipts WHERE hold_id=?", (hid,))
        conn.execute("DELETE FROM hold_transactions WHERE hold_id=?", (hid,))
    if hold_ids:
        conn.execute("DELETE FROM unit_holds WHERE unit_id=?", (unit_id,))
    conn.execute("DELETE FROM units WHERE id=?", (unit_id,))


IMPORT_FIELDS = (
    "unit_no", "unit_type", "residential_type", "floor_number", "block_tower",
    "area_ghaz", "bedrooms", "bathrooms", "base_sale_price", "booking_amount_required",
    "furnishing_status", "description", "unit_attributes",
)


def _import_row(raw: dict) -> dict:
    def pick(*names):
        for n in names:
            for key, val in raw.items():
                if str(key).strip().lower() == n:
                    return val
        return None

    def as_int(v):
        if v in (None, ""):
            return None
        return int(float(str(v).replace(",", "").strip()))

    def as_float(v):
        if v in (None, ""):
            return None
        return float(str(v).replace(",", "").strip())

    unit_no = str(pick("unit_no", "unit") or "").strip()
    if not unit_no:
        raise ValueError("unit_no is required")
    tags = pick("unit_attributes", "tags", "amenities")
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.replace("|", ";").split(";") if t.strip()]
    elif not isinstance(tags, list):
        tags = []
    return {
        "unit_no": unit_no,
        "unit_type": pick("unit_type", "type") or "residential",
        "residential_type": pick("residential_type", "layout") or None,
        "floor_number": as_int(pick("floor_number", "floor")) if pick("floor_number", "floor") not in (None, "") else 0,
        "block_tower": (str(pick("block_tower", "block") or "").strip() or None),
        "area_ghaz": as_float(pick("area_ghaz", "area")),
        "bedrooms": as_int(pick("bedrooms")),
        "bathrooms": as_int(pick("bathrooms")),
        "base_sale_price": as_int(pick("base_sale_price", "price")),
        "booking_amount_required": as_int(pick("booking_amount_required", "booking_amount")),
        "furnishing_status": (str(pick("furnishing_status", "furnishing") or "").strip() or None),
        "description": (str(pick("description") or "").strip() or None),
        "unit_attributes": tags,
        "status": "available",
    }


def import_units(conn, project_id: int, rows: list[dict]) -> dict:
    if not fetch_one(conn, "SELECT id FROM projects WHERE id=?", (project_id,)):
        raise ValueError("Project not found")
    created, errors = [], []
    for i, raw in enumerate(rows, start=2):
        try:
            data = _import_row(raw)
            data["project_id"] = project_id
            created.append(create_unit(conn, data))
        except (ValueError, TypeError) as e:
            errors.append({"row": i, "unit_no": str((raw or {}).get("unit_no") or ""), "error": str(e)})
    return {"created": len(created), "failed": len(errors), "errors": errors, "units": created}
