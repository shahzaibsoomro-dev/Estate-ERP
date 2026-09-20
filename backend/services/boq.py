"""Bill of Quantities — estimated material requirements, and how they compare to reality.

Estimates live here. Actual stock stays in Materials (inventory), actual buying in
Purchase Orders, actual usage in the site logs. A BOQ line links across to those by
material item, or failing that by name.
"""

import json

from backend.database import fetch_all, fetch_one
from backend.services import audit as audit_svc


def _clean(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _num(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value, default=0) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _key(name) -> str:
    return " ".join((name or "").lower().split())


def line_totals(line: dict) -> dict:
    qty = max(_num(line.get("qty")), 0.0)
    wastage = max(_num(line.get("wastage_pct")), 0.0)
    rate = max(_int(line.get("rate")), 0)
    estimated_qty = round(qty * (1 + wastage / 100), 4)
    return {
        "qty": qty,
        "wastage_pct": wastage,
        "rate": rate,
        "estimated_qty": estimated_qty,
        "estimated_amount": int(round(estimated_qty * rate)),
    }


# --------------------------------------------------------------- actuals
def _po_units(po: dict) -> float:
    """Best-effort quantity for a PO: pack maths first, else the first number typed."""
    units = _num(po.get("total_units"))
    if units > 0:
        return units
    for token in str(po.get("quantity") or "").replace(",", " ").split():
        try:
            return float(token)
        except ValueError:
            continue
    return 0.0


def _purchases(conn, project_id: int) -> list[dict]:
    rows = fetch_all(
        conn,
        """SELECT po.id, po.po_no, po.material, po.quantity, po.total_units, po.total,
                  po.budget_category_id, po.pack_unit, i.name AS item_name, i.id AS item_id
           FROM purchase_orders po
           LEFT JOIN inventory_movements m ON m.reference_type='po_grn' AND m.reference_id=po.id
           LEFT JOIN inventory_items i ON i.id=m.item_id
           WHERE po.project_id=? AND po.status!='cancelled'""",
        (project_id,),
    )
    for r in rows:
        r["units"] = _po_units(r)
        r["key"] = _key(r.get("item_name") or r.get("material"))
    return rows


def _issued_stock(conn, project_id: int) -> dict:
    """Material issued out of stock on this project, by item id."""
    rows = fetch_all(
        conn,
        """SELECT item_id, COALESCE(SUM(quantity),0) AS qty
           FROM inventory_movements
           WHERE direction='out' AND project_id=?
             AND (reference_type IS NULL OR reference_type NOT IN ('po_grn_reverse'))
           GROUP BY item_id""",
        (project_id,),
    )
    return {r["item_id"]: _num(r["qty"]) for r in rows}


def _site_usage(conn, project_id: int) -> dict:
    """Material the site logs say was used, by normalized name."""
    out: dict[str, float] = {}
    for row in fetch_all(
        conn, "SELECT materials_json FROM site_logs WHERE project_id=? AND materials_json IS NOT NULL", (project_id,)
    ):
        try:
            items = json.loads(row["materials_json"] or "[]")
        except json.JSONDecodeError:
            continue
        if not isinstance(items, list):
            continue
        for it in items:
            if not isinstance(it, dict):
                continue
            key = _key(it.get("name") or it.get("material"))
            if not key:
                continue
            out[key] = out.get(key, 0.0) + max(_num(it.get("qty") or it.get("quantity")), 0.0)
    return out


def _status_of(estimated: float, used: float) -> str:
    if estimated <= 0:
        return "No estimate"
    pct = used / estimated * 100
    if pct > 100:
        return "Over estimate"
    if pct >= 85:
        return "Near estimate"
    return "Within estimate"


# --------------------------------------------------------------- reads
_LINE_SQL = """SELECT bl.*, s.name AS stage_name, t.name AS task_name,
                      i.name AS item_name, i.unit AS item_unit, c.name AS category_name,
                      p.name AS project_name
               FROM project_boq_lines bl
               LEFT JOIN project_stages s ON s.id=bl.stage_id
               LEFT JOIN project_tasks t ON t.id=bl.task_id
               LEFT JOIN inventory_items i ON i.id=bl.item_id
               LEFT JOIN budget_categories c ON c.id=bl.category_id
               JOIN projects p ON p.id=bl.project_id
               WHERE bl.is_active=1"""


def list_lines(conn, project_id: int | None = None, project_ids: list[int] | None = None) -> list[dict]:
    q, params = _LINE_SQL, []
    if project_ids:
        q += f" AND bl.project_id IN ({','.join('?' * len(project_ids))})"
        params.extend(project_ids)
    elif project_id:
        q += " AND bl.project_id=?"
        params.append(project_id)
    q += " ORDER BY bl.project_id, s.sort_order, bl.id"
    rows = fetch_all(conn, q, tuple(params))
    for row in rows:
        row.update(line_totals(row))
    return rows


def get_line(conn, line_id: int) -> dict | None:
    row = fetch_one(conn, _LINE_SQL + " AND bl.id=?", (line_id,))
    if row:
        row.update(line_totals(row))
    return row


def compare(conn, project_id: int) -> list[dict]:
    """Per line: what we estimated, what we bought, what the site actually used."""
    lines = list_lines(conn, project_id)
    pos = _purchases(conn, project_id)
    issued = _issued_stock(conn, project_id)
    site = _site_usage(conn, project_id)
    for line in lines:
        keys = {_key(line.get("item_name")), _key(line.get("name"))} - {""}
        matched = [po for po in pos if po["key"] in keys]
        if not matched and line.get("category_id"):
            matched = [po for po in pos if not po["key"] and po.get("budget_category_id") == line["category_id"]]
        line["purchased_qty"] = round(sum(po["units"] for po in matched), 4)
        line["purchased_amount"] = int(sum(_int(po.get("total")) for po in matched))
        line["purchase_refs"] = [po["po_no"] for po in matched]
        stock_out = issued.get(line.get("item_id"), 0.0) if line.get("item_id") else 0.0
        logged = sum(site.get(k, 0.0) for k in keys)
        # Stock issues and site logs describe the same physical usage from two angles,
        # so the larger of the two is the honest consumption figure — not their sum.
        line["consumed_stock_qty"] = round(stock_out, 4)
        line["consumed_site_qty"] = round(logged, 4)
        line["consumed_qty"] = round(max(stock_out, logged), 4)
        line["remaining_qty"] = round(line["estimated_qty"] - line["consumed_qty"], 4)
        line["variance_amount"] = line["estimated_amount"] - line["purchased_amount"]
        line["usage_pct"] = (round(line["consumed_qty"] / line["estimated_qty"] * 100)
                             if line["estimated_qty"] else 0)
        line["status"] = _status_of(line["estimated_qty"], line["consumed_qty"])
    return lines


def summary(conn, project_id: int) -> dict:
    lines = compare(conn, project_id)
    by_category: dict = {}
    for line in lines:
        cid = line.get("category_id")
        bucket = by_category.setdefault(cid, {
            "category_id": cid,
            "category_name": line.get("category_name") or "Uncategorised",
            "estimated_amount": 0, "purchased_amount": 0, "line_count": 0,
        })
        bucket["estimated_amount"] += line["estimated_amount"]
        bucket["purchased_amount"] += line["purchased_amount"]
        bucket["line_count"] += 1
    return {
        "project_id": project_id,
        "line_count": len(lines),
        "estimated_amount": sum(line["estimated_amount"] for line in lines),
        "purchased_amount": sum(line["purchased_amount"] for line in lines),
        "over_estimate": sum(1 for line in lines if line["status"] == "Over estimate"),
        "categories": sorted(by_category.values(), key=lambda c: c["category_name"]),
        "lines": lines,
    }


def amount_by_category(conn, project_id: int) -> dict:
    """Estimated material cost per budget category — feeds the budget roll-up."""
    out: dict = {}
    for line in list_lines(conn, project_id):
        cid = line.get("category_id")
        out[cid] = out.get(cid, 0) + line["estimated_amount"]
    return out


# --------------------------------------------------------------- writes
def _resolve_links(conn, data: dict, project_id: int) -> tuple[int | None, int | None]:
    stage_id = _int(data.get("stage_id"), 0) or None
    task_id = _int(data.get("task_id"), 0) or None
    if task_id:
        task = fetch_one(conn, "SELECT project_id, stage_id FROM project_tasks WHERE id=?", (task_id,))
        if not task or task["project_id"] != project_id:
            raise ValueError("Task not found in this project")
        stage_id = stage_id or task["stage_id"]
    if stage_id:
        stage = fetch_one(conn, "SELECT project_id FROM project_stages WHERE id=?", (stage_id,))
        if not stage or stage["project_id"] != project_id:
            raise ValueError("Stage not found in this project")
    return stage_id, task_id


def _resolve_item(conn, data: dict) -> tuple[int | None, str | None, str | None]:
    item_id = _int(data.get("item_id"), 0) or None
    name = _clean(data.get("name"))
    unit = _clean(data.get("unit"))
    if item_id:
        item = fetch_one(conn, "SELECT name, unit FROM inventory_items WHERE id=?", (item_id,))
        if not item:
            raise ValueError("Material item not found")
        name = name or item["name"]
        unit = unit or item["unit"]
    if not name:
        raise ValueError("Line name is required")
    return item_id, name, unit or "pcs"


def create_line(conn, data: dict) -> dict:
    project_id = _int(data.get("project_id"), 0)
    if not project_id or not fetch_one(conn, "SELECT id FROM projects WHERE id=?", (project_id,)):
        raise ValueError("Project not found")
    stage_id, task_id = _resolve_links(conn, data, project_id)
    item_id, name, unit = _resolve_item(conn, data)
    category_id = _int(data.get("category_id"), 0) or None
    if category_id and not fetch_one(conn, "SELECT id FROM budget_categories WHERE id=?", (category_id,)):
        raise ValueError("Budget category not found")
    cur = conn.execute(
        """INSERT INTO project_boq_lines(project_id, stage_id, task_id, item_id, category_id,
           name, unit, qty, wastage_pct, rate, revision_no, is_active, notes)
           VALUES(?,?,?,?,?,?,?,?,?,?,1,1,?)""",
        (
            project_id, stage_id, task_id, item_id, category_id, name, unit,
            max(_num(data.get("qty")), 0.0), max(_num(data.get("wastage_pct")), 0.0),
            max(_int(data.get("rate")), 0), _clean(data.get("notes")),
        ),
    )
    audit_svc.log(conn, "boq_line", cur.lastrowid, "created", {"project_id": project_id, "name": name})
    return get_line(conn, cur.lastrowid)


def update_line(conn, line_id: int, data: dict) -> dict:
    old = fetch_one(conn, "SELECT * FROM project_boq_lines WHERE id=?", (line_id,))
    if not old:
        raise ValueError("BOQ line not found")
    merged = {**old, **{k: v for k, v in data.items() if v is not None}}
    stage_id, task_id = _resolve_links(conn, merged, old["project_id"])
    item_id, name, unit = _resolve_item(conn, merged)
    category_id = _int(merged.get("category_id"), 0) or None
    revision = _int(old.get("revision_no"), 1)
    if _num(merged.get("qty")) != _num(old.get("qty")) or _int(merged.get("rate")) != _int(old.get("rate")):
        revision += 1
    conn.execute(
        """UPDATE project_boq_lines SET stage_id=?, task_id=?, item_id=?, category_id=?, name=?,
           unit=?, qty=?, wastage_pct=?, rate=?, revision_no=?, notes=? WHERE id=?""",
        (
            stage_id, task_id, item_id, category_id, name, unit,
            max(_num(merged.get("qty")), 0.0), max(_num(merged.get("wastage_pct")), 0.0),
            max(_int(merged.get("rate")), 0), revision, _clean(merged.get("notes")), line_id,
        ),
    )
    return get_line(conn, line_id)


def delete_line(conn, line_id: int) -> None:
    old = fetch_one(conn, "SELECT * FROM project_boq_lines WHERE id=?", (line_id,))
    if not old:
        raise ValueError("BOQ line not found")
    conn.execute("UPDATE project_boq_lines SET is_active=0 WHERE id=?", (line_id,))
    audit_svc.log(conn, "boq_line", line_id, "removed", {"name": old["name"]})
