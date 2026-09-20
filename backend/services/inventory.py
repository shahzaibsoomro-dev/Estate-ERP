"""Material inventory with stock movements (GRN / issue / adjust)."""

from datetime import date

from backend.database import fetch_all, fetch_one
from backend.services import audit as audit_svc


def _clean(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _qty(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def stock_on_hand(conn, item_id: int) -> float:
    row = fetch_one(
        conn,
        """SELECT COALESCE(SUM(CASE WHEN direction='in' THEN quantity
                                    WHEN direction='out' THEN -quantity
                                    ELSE 0 END), 0) AS v
           FROM inventory_movements WHERE item_id=?""",
        (item_id,),
    )
    return float(row["v"] if row else 0)


def _enrich_item(conn, item: dict) -> dict:
    item["on_hand"] = stock_on_hand(conn, item["id"])
    item["master_id"] = f"MAT-{item['id']}"
    if item.get("project_id"):
        proj = fetch_one(conn, "SELECT name FROM projects WHERE id=?", (item["project_id"],))
        item["project_name"] = proj["name"] if proj else None
    else:
        item["project_name"] = "Company"
    low = float(item.get("min_stock") or 0)
    item["low_stock"] = low > 0 and item["on_hand"] < low
    return item


def list_items(conn, project_id: int | None = None, project_ids: list[int] | None = None) -> list[dict]:
    q = "SELECT * FROM inventory_items WHERE status!='archived'"
    params: list = []
    if project_ids:
        ph = ",".join("?" * len(project_ids))
        q += f" AND (project_id IN ({ph}) OR project_id IS NULL)"
        params.extend(project_ids)
    elif project_id:
        q += " AND (project_id=? OR project_id IS NULL)"
        params.append(project_id)
    q += " ORDER BY name"
    return [_enrich_item(conn, r) for r in fetch_all(conn, q, tuple(params))]


def get_item(conn, item_id: int) -> dict | None:
    item = fetch_one(conn, "SELECT * FROM inventory_items WHERE id=?", (item_id,))
    if not item:
        return None
    _enrich_item(conn, item)
    item["movements"] = fetch_all(
        conn,
        """SELECT m.*, p.name AS project_name
           FROM inventory_movements m
           LEFT JOIN projects p ON p.id=m.project_id
           WHERE m.item_id=?
           ORDER BY m.movement_date DESC, m.id DESC""",
        (item_id,),
    )
    return item


def create_item(conn, data: dict) -> dict:
    name = _clean(data.get("name"))
    if not name:
        raise ValueError("Item name is required")
    project_id = data.get("project_id")
    if project_id in ("", None):
        project_id = None
    else:
        project_id = int(project_id)
        if not fetch_one(conn, "SELECT id FROM projects WHERE id=?", (project_id,)):
            raise ValueError("Project not found")
    cur = conn.execute(
        """INSERT INTO inventory_items(sku, name, unit, category, project_id, min_stock, notes, status)
           VALUES(?,?,?,?,?,?,?,?)""",
        (
            _clean(data.get("sku")), name, _clean(data.get("unit")) or "pcs",
            _clean(data.get("category")), project_id, _qty(data.get("min_stock")),
            _clean(data.get("notes")), "active",
        ),
    )
    item_id = cur.lastrowid
    opening = _qty(data.get("opening_stock") or data.get("on_hand"))
    if opening > 0:
        _add_movement(conn, item_id, {
            "direction": "in",
            "quantity": opening,
            "project_id": project_id,
            "unit_cost": int(data.get("unit_cost") or 0),
            "reference_type": "opening",
            "movement_date": date.today().isoformat(),
            "notes": "Opening stock",
        })
    audit_svc.log(conn, "inventory_item", item_id, "created", {"name": name})
    return get_item(conn, item_id)


def update_item(conn, item_id: int, data: dict) -> dict | None:
    if not fetch_one(conn, "SELECT id FROM inventory_items WHERE id=?", (item_id,)):
        return None
    name = _clean(data.get("name"))
    if not name:
        raise ValueError("Item name is required")
    project_id = data.get("project_id")
    if project_id in ("", None):
        project_id = None
    else:
        project_id = int(project_id)
    conn.execute(
        """UPDATE inventory_items SET sku=?, name=?, unit=?, category=?, project_id=?,
           min_stock=?, notes=?, status=? WHERE id=?""",
        (
            _clean(data.get("sku")), name, _clean(data.get("unit")) or "pcs",
            _clean(data.get("category")), project_id, _qty(data.get("min_stock")),
            _clean(data.get("notes")), _clean(data.get("status")) or "active", item_id,
        ),
    )
    return get_item(conn, item_id)


def _add_movement(conn, item_id: int, data: dict) -> int:
    direction = (_clean(data.get("direction")) or "").lower()
    if direction not in ("in", "out", "adjust"):
        raise ValueError("Direction must be in, out, or adjust")
    qty = abs(_qty(data.get("quantity")))
    if qty <= 0:
        raise ValueError("Quantity must be greater than 0")
    if direction == "adjust":
        # positive qty = set absolute? treat as in/out delta via signed? keep simple: adjust uses direction from sign
        direction = "in"
    project_id = data.get("project_id")
    if project_id in ("", None):
        project_id = None
    else:
        project_id = int(project_id)
    if direction == "out":
        on_hand = stock_on_hand(conn, item_id)
        if qty > on_hand + 1e-9:
            raise ValueError(f"Insufficient stock (on hand {on_hand})")
    try:
        unit_cost = int(data.get("unit_cost") or 0)
    except (TypeError, ValueError):
        unit_cost = 0
    cur = conn.execute(
        """INSERT INTO inventory_movements(
             item_id, project_id, direction, quantity, unit_cost,
             reference_type, reference_id, movement_date, notes)
           VALUES(?,?,?,?,?,?,?,?,?)""",
        (
            item_id, project_id, direction, qty, unit_cost,
            _clean(data.get("reference_type")), data.get("reference_id"),
            _clean(data.get("movement_date")) or date.today().isoformat(),
            _clean(data.get("notes")),
        ),
    )
    return cur.lastrowid


def add_movement(conn, item_id: int, data: dict) -> dict:
    if not fetch_one(conn, "SELECT id FROM inventory_items WHERE id=?", (item_id,)):
        raise ValueError("Inventory item not found")
    mid = _add_movement(conn, item_id, data)
    audit_svc.log(conn, "inventory_item", item_id, "movement", {
        "movement_id": mid, "direction": data.get("direction"), "quantity": data.get("quantity"),
    })
    return get_item(conn, item_id)


def receive_from_po(conn, po_id: int) -> dict | None:
    """Create/update inventory item and stock-in when a PO is GRN'd."""
    po = fetch_one(
        conn,
        """SELECT po.*, v.name AS vendor_name FROM purchase_orders po
           JOIN vendors v ON v.id=po.vendor_id WHERE po.id=?""",
        (po_id,),
    )
    if not po:
        return None
    material = _clean(po.get("material")) or f"PO {po.get('po_no')}"
    # Match existing project-scoped item by name
    item = fetch_one(
        conn,
        """SELECT * FROM inventory_items
           WHERE lower(name)=lower(?) AND (project_id=? OR (? IS NULL AND project_id IS NULL))
           ORDER BY id LIMIT 1""",
        (material, po["project_id"], po["project_id"]),
    )
    # Prefer pack math (2 × 10kg = 20 kg); fall back to first number in quantity.
    qty = _qty(po.get("total_units"))
    if qty <= 0:
        qty_raw = _clean(po.get("quantity")) or "1"
        qty = 1.0
        for token in qty_raw.replace(",", " ").split():
            try:
                qty = float(token)
                break
            except ValueError:
                continue
    item_unit = _clean(po.get("pack_unit")) or (item.get("unit") if item else None) or "kg"
    if not item:
        cur = conn.execute(
            """INSERT INTO inventory_items(sku, name, unit, category, project_id, min_stock, notes, status)
               VALUES(?,?,?,?,?,?,?,?)""",
            (
                po.get("po_no"), material, item_unit, po.get("category"),
                po["project_id"], 0, f"Auto from {po.get('po_no')}", "active",
            ),
        )
        item_id = cur.lastrowid
    else:
        item_id = item["id"]
    unit_cost = int(po.get("unit_cost") or 0)
    if unit_cost <= 0 and po.get("total") and qty:
        unit_cost = int(round(po["total"] / qty))
    # Avoid double GRN stock if already received for this PO
    existing = fetch_one(
        conn,
        """SELECT id FROM inventory_movements
           WHERE reference_type='po_grn' AND reference_id=?""",
        (po_id,),
    )
    if existing:
        return get_item(conn, item_id)
    _add_movement(conn, item_id, {
        "direction": "in",
        "quantity": qty,
        "project_id": po["project_id"],
        "unit_cost": unit_cost,
        "reference_type": "po_grn",
        "reference_id": po_id,
        "movement_date": date.today().isoformat(),
        "notes": f"GRN · {po.get('po_no')} · {po.get('vendor_name')}",
    })
    return get_item(conn, item_id)


def reverse_po_grn(conn, po_id: int) -> None:
    """Take GRN'd stock back out when a received PO is cancelled."""
    existing = fetch_one(
        conn,
        """SELECT * FROM inventory_movements
           WHERE reference_type='po_grn' AND reference_id=?
           ORDER BY id DESC LIMIT 1""",
        (po_id,),
    )
    if not existing:
        return
    already = fetch_one(
        conn,
        """SELECT id FROM inventory_movements
           WHERE reference_type='po_grn_reverse' AND reference_id=?""",
        (po_id,),
    )
    if already:
        return
    _add_movement(conn, existing["item_id"], {
        "direction": "out",
        "quantity": existing["quantity"],
        "project_id": existing["project_id"],
        "unit_cost": existing["unit_cost"],
        "reference_type": "po_grn_reverse",
        "reference_id": po_id,
        "movement_date": date.today().isoformat(),
        "notes": f"Reverse GRN · cancelled PO",
    })
