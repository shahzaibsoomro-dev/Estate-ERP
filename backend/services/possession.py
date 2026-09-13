"""Possession handover checklists."""

from datetime import date, datetime

from backend.database import fetch_all, fetch_one
from backend.services import audit as audit_svc


def _clean(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def list_templates(conn) -> list[dict]:
    tmpls = fetch_all(
        conn, "SELECT * FROM possession_checklist_templates ORDER BY is_default DESC, id"
    )
    for t in tmpls:
        t["items"] = fetch_all(
            conn,
            """SELECT * FROM possession_checklist_template_items
               WHERE template_id=? ORDER BY sort_order, id""",
            (t["id"],),
        )
        t["item_count"] = len(t["items"])
    return tmpls


def get_default_template(conn) -> dict | None:
    tmpl = fetch_one(
        conn,
        "SELECT * FROM possession_checklist_templates WHERE is_default=1 ORDER BY id LIMIT 1",
    )
    if not tmpl:
        tmpl = fetch_one(conn, "SELECT * FROM possession_checklist_templates ORDER BY id LIMIT 1")
    if not tmpl:
        return None
    tmpl = dict(tmpl)
    tmpl["items"] = fetch_all(
        conn,
        """SELECT * FROM possession_checklist_template_items
           WHERE template_id=? ORDER BY sort_order, id""",
        (tmpl["id"],),
    )
    return tmpl


def save_template(conn, data: dict, template_id: int | None = None) -> dict:
    name = _clean(data.get("name"))
    if not name:
        raise ValueError("Template name is required")
    items = data.get("items") or []
    if not items:
        raise ValueError("Add at least one checklist item")
    is_default = 1 if data.get("is_default") else 0
    if is_default:
        conn.execute("UPDATE possession_checklist_templates SET is_default=0")
    if template_id:
        if not fetch_one(conn, "SELECT id FROM possession_checklist_templates WHERE id=?", (template_id,)):
            raise ValueError("Template not found")
        conn.execute(
            "UPDATE possession_checklist_templates SET name=?, is_default=? WHERE id=?",
            (name, is_default, template_id),
        )
        conn.execute(
            "DELETE FROM possession_checklist_template_items WHERE template_id=?", (template_id,),
        )
        tid = template_id
    else:
        cur = conn.execute(
            "INSERT INTO possession_checklist_templates(name, is_default) VALUES(?,?)",
            (name, is_default),
        )
        tid = cur.lastrowid
    for i, raw in enumerate(items, start=1):
        if isinstance(raw, str):
            label, required = raw, 1
        else:
            label = _clean(raw.get("label"))
            required = 1 if raw.get("is_required", True) else 0
        if not label:
            continue
        conn.execute(
            """INSERT INTO possession_checklist_template_items(template_id, sort_order, label, is_required)
               VALUES(?,?,?,?)""",
            (tid, i, label, required),
        )
    return next(t for t in list_templates(conn) if t["id"] == tid)


def get_checklist(conn, checklist_id: int) -> dict | None:
    row = fetch_one(
        conn,
        """SELECT pc.*, u.unit_no, p.name AS project_name, c.name AS customer_name, b.booking_no
           FROM possession_checklists pc
           JOIN units u ON u.id=pc.unit_id
           JOIN projects p ON p.id=u.project_id
           JOIN bookings b ON b.id=pc.booking_id
           JOIN customers c ON c.id=b.customer_id
           WHERE pc.id=?""",
        (checklist_id,),
    )
    if not row:
        return None
    row["responses"] = fetch_all(
        conn,
        """SELECT * FROM possession_checklist_responses
           WHERE checklist_id=? ORDER BY id""",
        (checklist_id,),
    )
    total = len(row["responses"])
    done = sum(1 for r in row["responses"] if r.get("checked"))
    row["progress"] = {"done": done, "total": total, "pct": int(done / total * 100) if total else 0}
    return row


def get_checklist_for_unit(conn, unit_id: int) -> dict | None:
    row = fetch_one(
        conn,
        """SELECT id FROM possession_checklists WHERE unit_id=?
           ORDER BY id DESC LIMIT 1""",
        (unit_id,),
    )
    return get_checklist(conn, row["id"]) if row else None


def start_checklist(conn, unit_id: int, possession_date: str | None = None,
                    template_id: int | None = None, completed_by: str | None = None) -> dict:
    booking = fetch_one(
        conn,
        "SELECT * FROM bookings WHERE unit_id=? AND status='active' ORDER BY id DESC LIMIT 1",
        (unit_id,),
    )
    if not booking:
        raise ValueError("Active booking required for possession checklist")
    existing = fetch_one(
        conn,
        """SELECT id FROM possession_checklists
           WHERE unit_id=? AND booking_id=? AND status='in_progress'
           ORDER BY id DESC LIMIT 1""",
        (unit_id, booking["id"]),
    )
    if existing:
        return get_checklist(conn, existing["id"])

    tmpl = None
    if template_id:
        row = fetch_one(conn, "SELECT * FROM possession_checklist_templates WHERE id=?", (template_id,))
        if row:
            tmpl = dict(row)
            tmpl["items"] = fetch_all(
                conn,
                """SELECT * FROM possession_checklist_template_items
                   WHERE template_id=? ORDER BY sort_order, id""",
                (template_id,),
            )
    if not tmpl:
        tmpl = get_default_template(conn)
    if not tmpl or not tmpl.get("items"):
        raise ValueError("No possession checklist template configured")

    when = _clean(possession_date) or date.today().isoformat()
    cur = conn.execute(
        """INSERT INTO possession_checklists(
             booking_id, unit_id, template_id, possession_date, status, completed_by, notes)
           VALUES(?,?,?,?, 'in_progress', ?, NULL)""",
        (booking["id"], unit_id, tmpl["id"], when, _clean(completed_by)),
    )
    checklist_id = cur.lastrowid
    for item in tmpl["items"]:
        conn.execute(
            """INSERT INTO possession_checklist_responses(
                 checklist_id, item_id, label, is_required, checked)
               VALUES(?,?,?,?,0)""",
            (checklist_id, item["id"], item["label"], item.get("is_required", 1)),
        )
    audit_svc.log(conn, "possession_checklist", checklist_id, "started", {
        "unit_id": unit_id, "booking_id": booking["id"],
    })
    return get_checklist(conn, checklist_id)


def update_responses(conn, checklist_id: int, responses: list[dict],
                     notes: str | None = None, completed_by: str | None = None) -> dict:
    cl = fetch_one(conn, "SELECT * FROM possession_checklists WHERE id=?", (checklist_id,))
    if not cl:
        raise ValueError("Checklist not found")
    for raw in responses or []:
        rid = raw.get("id")
        if not rid:
            continue
        checked = 1 if raw.get("checked") else 0
        conn.execute(
            """UPDATE possession_checklist_responses SET checked=?, notes=?
               WHERE id=? AND checklist_id=?""",
            (checked, _clean(raw.get("notes")), rid, checklist_id),
        )
    if notes is not None or completed_by is not None:
        conn.execute(
            """UPDATE possession_checklists SET notes=COALESCE(?, notes),
               completed_by=COALESCE(?, completed_by) WHERE id=?""",
            (_clean(notes), _clean(completed_by), checklist_id),
        )
    return get_checklist(conn, checklist_id)


def complete_checklist(conn, checklist_id: int, completed_by: str | None = None,
                       force: bool = False) -> dict:
    cl = get_checklist(conn, checklist_id)
    if not cl:
        raise ValueError("Checklist not found")
    missing = [
        r["label"] for r in cl["responses"]
        if r.get("is_required") and not r.get("checked")
    ]
    if missing and not force:
        raise ValueError("Required items not checked: " + ", ".join(missing[:5]))
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """UPDATE possession_checklists SET status='completed', completed_at=?,
           completed_by=COALESCE(?, completed_by) WHERE id=?""",
        (now, _clean(completed_by), checklist_id),
    )
    audit_svc.log(conn, "possession_checklist", checklist_id, "completed", {})
    return get_checklist(conn, checklist_id)
