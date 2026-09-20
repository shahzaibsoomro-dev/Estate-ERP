from datetime import date

from backend.database import fetch_all, fetch_one
from backend.services import audit as audit_svc
from backend.services.project_filter import sql_in


def _clean(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_vendor(data: dict) -> dict:
    name = _clean(data.get("name"))
    if not name:
        raise ValueError("Vendor name is required")
    status = (_clean(data.get("status")) or "active").lower()
    if status not in ("active", "inactive"):
        status = "active"
    return {
        "name": name,
        "description": _clean(data.get("description")),
        "contact": _clean(data.get("contact")),
        "category": _clean(data.get("category")),
        "ntn": _clean(data.get("ntn")),
        "status": status,
    }


def list_vendors(conn) -> list[dict]:
    vendors = fetch_all(conn, "SELECT * FROM vendors ORDER BY name")
    for v in vendors:
        _attach_balances(conn, v)
    return vendors


def _qty_num(value) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    for token in str(value).replace(",", " ").split():
        try:
            return float(token)
        except ValueError:
            continue
    return None


def compute_pack_units(data: dict) -> tuple[float | None, float, str | None, float | None, str]:
    """2 packs × 10 kg = 20 kg. pack_size defaults to 1 when omitted."""
    qty_text = _clean(data.get("qty") or data.get("quantity"))
    packs = _qty_num(data.get("pack_qty"))
    if packs is None:
        packs = _qty_num(qty_text)
    size = _qty_num(data.get("pack_size"))
    if size is None or size <= 0:
        size = 1.0
    unit = _clean(data.get("pack_unit"))
    if not unit and qty_text:
        tokens = qty_text.replace("×", "x").replace("=", " ").split()
        unit = next(
            (t for t in reversed(tokens) if _qty_num(t) is None and t.lower() not in ("x",)),
            None,
        )
    if not unit:
        unit = "kg" if size != 1 else "pcs"
    if not packs:
        return None, size, unit, None, qty_text or "—"
    total_units = round(packs * size, 6)
    if size != 1:
        label = f"{packs:g} × {size:g} {unit} = {total_units:g} {unit}"
    else:
        label = f"{packs:g} {unit}".strip()
    return packs, size, unit, total_units, label


def _attach_balances(conn, vendor: dict) -> dict:
    pos = fetch_one(
        conn,
        """SELECT COALESCE(SUM(CASE WHEN status!='cancelled' THEN total
                                    ELSE COALESCE(cancel_fee_amount,0) END),0) AS total_payable
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
    vendor["master_id"] = f"VEN-{vendor['id']}"
    return vendor


def _po_paid(conn, po_id: int) -> int:
    row = fetch_one(
        conn,
        "SELECT COALESCE(SUM(amount),0) AS v FROM vendor_payments WHERE purchase_order_id=?",
        (po_id,),
    )
    return row["v"] if row else 0


def _map_po_status(po: dict, paid: int = 0) -> dict:
    """Map internal status to UI: draft | approved | payment_pending | completed | cancelled."""
    status = po.get("status", "ordered")
    grn = po.get("grn_status", "pending")
    po["paid"] = paid
    po["remaining"] = max((po.get("total") or 0) - paid, 0)
    if status == "cancelled":
        po["status"] = "cancelled"
        po["remaining"] = 0
        return po
    if status == "closed":
        po["status"] = "completed"
        po["grn_status"] = "done"
    elif status == "delivered" or grn == "done":
        po["grn_status"] = "done"
        po["status"] = "completed" if paid >= (po.get("total") or 0) else "payment_pending"
    elif grn == "na":
        po["status"] = "draft"
    else:
        po["status"] = "approved"
    return po


def _mapped_po(conn, po: dict) -> dict:
    row = _map_po_status(dict(po), _po_paid(conn, po["id"]))
    packs = row.get("pack_qty")
    size = row.get("pack_size") or 1
    unit = row.get("pack_unit") or ""
    total_units = row.get("total_units")
    if packs and total_units is None:
        total_units = float(packs) * float(size)
        row["total_units"] = total_units
    if packs and size and float(size) != 1 and unit:
        row["qty_label"] = f"{float(packs):g} × {float(size):g} {unit} = {float(total_units or 0):g} {unit}"
    elif packs and unit:
        row["qty_label"] = f"{float(packs):g} {unit}"
    else:
        row["qty_label"] = row.get("quantity") or "—"
    if total_units and row.get("total"):
        row["unit_cost_per_unit"] = int(round(row["total"] / float(total_units)))
    else:
        row["unit_cost_per_unit"] = None
    return row


def _check_ntn(conn, ntn, vendor_id=None):
    if ntn and fetch_one(conn, "SELECT id FROM vendors WHERE ntn=? AND id != ?", (ntn, vendor_id or 0)):
        raise ValueError(f"Another vendor already has NTN {ntn}")


def create_vendor(conn, data: dict) -> dict:
    payload = normalize_vendor(data)
    _check_ntn(conn, payload["ntn"])
    cur = conn.execute(
        "INSERT INTO vendors(name, description, contact, category, ntn, status) VALUES(?,?,?,?,?,?)",
        (
            payload["name"], payload["description"], payload["contact"],
            payload["category"], payload["ntn"], payload["status"],
        ),
    )
    return get_vendor(conn, cur.lastrowid)


def get_vendor(conn, vendor_id: int) -> dict | None:
    v = fetch_one(conn, "SELECT * FROM vendors WHERE id=?", (vendor_id,))
    if not v:
        return None
    _attach_balances(conn, v)
    pos = fetch_all(
        conn,
        """SELECT po.*, p.name AS project_name
           FROM purchase_orders po
           JOIN projects p ON p.id=po.project_id
           WHERE po.vendor_id=?
           ORDER BY po.order_date DESC""",
        (vendor_id,),
    )
    v["purchase_orders"] = [_mapped_po(conn, po) for po in pos]
    v["payments"] = fetch_all(
        conn,
        """SELECT vp.*, po.po_no
           FROM vendor_payments vp
           LEFT JOIN purchase_orders po ON po.id=vp.purchase_order_id
           WHERE vp.vendor_id=?
           ORDER BY vp.payment_date DESC""",
        (vendor_id,),
    )
    return v


def update_vendor(conn, vendor_id: int, data: dict) -> dict | None:
    if not fetch_one(conn, "SELECT id FROM vendors WHERE id=?", (vendor_id,)):
        return None
    payload = normalize_vendor(data)
    _check_ntn(conn, payload["ntn"], vendor_id)
    conn.execute(
        """UPDATE vendors SET name=?, description=?, contact=?, category=?, ntn=?, status=?
           WHERE id=?""",
        (
            payload["name"], payload["description"], payload["contact"],
            payload["category"], payload["ntn"], payload["status"], vendor_id,
        ),
    )
    return get_vendor(conn, vendor_id)


def delete_vendor(conn, vendor_id: int) -> None:
    if not fetch_one(conn, "SELECT id FROM vendors WHERE id=?", (vendor_id,)):
        raise ValueError("Vendor not found")
    if fetch_one(conn, "SELECT id FROM purchase_orders WHERE vendor_id=? LIMIT 1", (vendor_id,)):
        raise ValueError("Cannot delete a vendor with purchase orders")
    if fetch_one(conn, "SELECT id FROM vendor_payments WHERE vendor_id=? LIMIT 1", (vendor_id,)):
        raise ValueError("Cannot delete a vendor with payment history")
    conn.execute("DELETE FROM vendors WHERE id=?", (vendor_id,))


def list_purchase_orders(conn, project_ids: list[int] | None = None) -> list[dict]:
    q = """SELECT po.*, v.name AS vendor_name, p.name AS project_name
           FROM purchase_orders po
           JOIN vendors v ON v.id=po.vendor_id
           JOIN projects p ON p.id=po.project_id
           WHERE 1=1"""
    clause, params = sql_in("po.project_id", project_ids)
    q += clause + " ORDER BY po.order_date DESC, po.id DESC"
    return [_mapped_po(conn, r) for r in fetch_all(conn, q, params)]


def get_purchase_order(conn, po_id: int) -> dict | None:
    po = fetch_one(
        conn,
        """SELECT po.*, v.name AS vendor_name, p.name AS project_name
           FROM purchase_orders po
           JOIN vendors v ON v.id=po.vendor_id
           JOIN projects p ON p.id=po.project_id
           WHERE po.id=?""",
        (po_id,),
    )
    return _mapped_po(conn, po) if po else None


def next_po_no(conn) -> str:
    year = date.today().year
    prefix = f"PO-{year}-"
    row = fetch_one(
        conn,
        "SELECT po_no FROM purchase_orders WHERE po_no LIKE ? ORDER BY po_no DESC LIMIT 1",
        (prefix + "%",),
    )
    n = 1
    if row and row["po_no"]:
        try:
            n = int(str(row["po_no"]).split("-")[-1]) + 1
        except ValueError:
            n = 1
    return f"{prefix}{n:04d}"


def create_purchase_order(conn, data: dict) -> dict:
    vendor_id = data.get("vendor_id")
    project_id = data.get("project_id")
    material = _clean(data.get("material"))
    if not vendor_id or not project_id or not material:
        raise ValueError("Vendor, project and material are required")
    if not fetch_one(conn, "SELECT id FROM vendors WHERE id=?", (vendor_id,)):
        raise ValueError("Vendor not found")
    if not fetch_one(conn, "SELECT id FROM projects WHERE id=?", (project_id,)):
        raise ValueError("Project not found")
    packs, size, unit, total_units, qty_label = compute_pack_units(data)
    total = data.get("total")
    unit_cost = data.get("unit_cost")
    if total in (None, ""):
        try:
            total = int(round((unit_cost or 0) * packs)) if packs else 0
        except (TypeError, ValueError):
            total = 0
    total = int(total or 0)
    if total <= 0:
        raise ValueError("Total must be greater than 0")
    po_no = _clean(data.get("po_no")) or next_po_no(conn)
    if fetch_one(conn, "SELECT id FROM purchase_orders WHERE po_no=?", (po_no,)):
        raise ValueError("PO number already exists")
    order_date = _clean(data.get("order_date")) or date.today().isoformat()
    cur = conn.execute(
        """INSERT INTO purchase_orders(po_no, vendor_id, project_id, budget_category_id,
           category, material, quantity, pack_qty, pack_size, pack_unit, total_units,
           unit_cost, total, order_date,
           expected_delivery_date, status, grn_status, site, notes)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            po_no, vendor_id, project_id,
            data.get("budget_category_id"), data.get("category"), material,
            qty_label, packs or None, size, unit, total_units or None,
            unit_cost, total, order_date,
            _clean(data.get("expected_delivery_date")),
            "ordered", "na",
            _clean(data.get("site")), _clean(data.get("notes")),
        ),
    )
    return get_purchase_order(conn, cur.lastrowid)


def cancel_preview(conn, po_id: int) -> dict | None:
    po = get_purchase_order(conn, po_id)
    if not po:
        return None
    from backend.services import settings as settings_svc
    default_pct = settings_svc.get_float(conn, "po_cancel_fee_pct", 30.0)
    paid = po.get("paid") or 0
    fee = int(round(paid * default_pct / 100.0)) if paid else 0
    refund = max(paid - fee, 0)
    return {
        **po,
        "default_fee_pct": default_pct,
        "paid": paid,
        "suggested_fee": fee,
        "suggested_refund": refund,
        "needs_confirm": paid > 0,
        "grn_done": po.get("grn_status") == "done",
    }


def _cancel_po(conn, po: dict, fee_pct: float | None, reason: str | None) -> dict:
    from backend.services import settings as settings_svc
    mapped = _map_po_status(dict(po), _po_paid(conn, po["id"]))
    if mapped["status"] == "cancelled":
        raise ValueError("Purchase order is already cancelled")
    paid = _po_paid(conn, po["id"])
    default_pct = settings_svc.get_float(conn, "po_cancel_fee_pct", 30.0)
    if paid > 0 and fee_pct is None:
        fee = int(round(paid * default_pct / 100.0))
        refund = paid - fee
        raise ValueError(
            f"This PO has PKR {paid:,} paid. Confirm cancel with cancel_fee_pct "
            f"(default {default_pct:g}%: vendor keeps PKR {fee:,}, refund PKR {refund:,})."
        )
    pct = default_pct if fee_pct is None else float(fee_pct)
    if pct < 0 or pct > 100:
        raise ValueError("Cancellation fee must be between 0 and 100 percent")
    fee = int(round(paid * pct / 100.0)) if paid else 0
    refund = max(paid - fee, 0)
    if mapped.get("grn_status") == "done":
        from backend.services import inventory as inv_svc
        inv_svc.reverse_po_grn(conn, po["id"])
    if refund > 0:
        conn.execute(
            """INSERT INTO vendor_payments(vendor_id, purchase_order_id, amount,
               payment_date, payment_method, reference_number, notes)
               VALUES(?,?,?,?,?,?,?)""",
            (
                po["vendor_id"], po["id"], -refund, date.today().isoformat(),
                "Bank Transfer", po.get("po_no"),
                f"PO cancel refund · vendor kept {pct:g}% (PKR {fee:,})",
            ),
        )
    conn.execute(
        """UPDATE purchase_orders SET status='cancelled',
           cancel_fee_pct=?, cancel_fee_amount=?, cancel_refund_amount=?,
           cancelled_at=datetime('now'), cancel_reason=?
           WHERE id=?""",
        (pct, fee, refund, _clean(reason), po["id"]),
    )
    audit_svc.log(conn, "purchase_order", po["id"], "cancelled", {
        "po_no": po.get("po_no"), "paid": paid, "fee_pct": pct, "fee": fee, "refund": refund,
    })
    return get_purchase_order(conn, po["id"])


def update_po_status(conn, po_id: int, status: str, extra: dict | None = None) -> dict | None:
    po = fetch_one(conn, "SELECT * FROM purchase_orders WHERE id=?", (po_id,))
    if not po:
        return None
    extra = extra or {}
    key = (status or "").lower()
    if key == "approved":
        conn.execute(
            "UPDATE purchase_orders SET status='ordered', grn_status='pending' WHERE id=?",
            (po_id,),
        )
    elif key in ("grn", "payment_pending"):
        conn.execute(
            "UPDATE purchase_orders SET status='delivered', grn_status='done' WHERE id=?",
            (po_id,),
        )
        try:
            from backend.services import inventory as inv_svc
            inv_svc.receive_from_po(conn, po_id)
        except Exception:
            pass
    elif key == "completed":
        conn.execute(
            "UPDATE purchase_orders SET status='closed', grn_status='done' WHERE id=?",
            (po_id,),
        )
    elif key == "cancelled":
        raw_pct = extra.get("cancel_fee_pct")
        if raw_pct in ("", None):
            raw_pct = None
        else:
            try:
                raw_pct = float(raw_pct)
            except (TypeError, ValueError) as e:
                raise ValueError("Cancellation fee must be a number") from e
        return _cancel_po(conn, po, raw_pct, extra.get("cancel_reason"))
    else:
        raise ValueError("Invalid PO status")
    return get_purchase_order(conn, po_id)


def record_vendor_payment(conn, data: dict) -> dict:
    vendor_id = data.get("vendor_id")
    amount = int(data.get("amount") or 0)
    pay_date = _clean(data.get("payment_date")) or date.today().isoformat()
    if not vendor_id:
        raise ValueError("Vendor is required")
    if amount <= 0:
        raise ValueError("Amount must be greater than 0")
    if not fetch_one(conn, "SELECT id FROM vendors WHERE id=?", (vendor_id,)):
        raise ValueError("Vendor not found")
    po_id = data.get("purchase_order_id")
    if po_id:
        po = get_purchase_order(conn, po_id)
        if not po:
            raise ValueError("Purchase order not found")
        if po["vendor_id"] != vendor_id:
            raise ValueError("PO does not belong to this vendor")
        if amount > (po.get("remaining") or 0):
            raise ValueError("Payment exceeds remaining PO amount")
    cur = conn.execute(
        """INSERT INTO vendor_payments(vendor_id, purchase_order_id, amount,
           payment_date, payment_method, reference_number, notes)
           VALUES(?,?,?,?,?,?,?)""",
        (
            vendor_id, po_id, amount, pay_date,
            _clean(data.get("payment_method")) or "Bank Transfer",
            _clean(data.get("reference_number")), _clean(data.get("notes")),
        ),
    )
    if po_id:
        po = get_purchase_order(conn, po_id)
        if po and (po.get("remaining") or 0) <= 0:
            conn.execute(
                "UPDATE purchase_orders SET status='closed', grn_status='done' WHERE id=?",
                (po_id,),
            )
    audit_svc.log(conn, "vendor_payment", cur.lastrowid, "recorded", {
        "vendor_id": vendor_id, "amount": amount, "purchase_order_id": po_id,
    })
    return {"ok": True, "id": cur.lastrowid}
