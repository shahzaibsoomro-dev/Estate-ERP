from backend.database import fetch_all, fetch_one

PROJECT_TYPES = ("building", "housing_scheme")
PROJECT_STATUSES = ("planning", "under_construction", "completed")
STATUS_LABELS = {
    "planning": "Planning",
    "under_construction": "Under construction",
    "completed": "Completed",
}
TYPE_LABELS = {
    "building": "Building",
    "housing_scheme": "Housing scheme",
}


def _int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_status(raw) -> str:
    status = (raw or "planning").strip().lower().replace(" ", "_")
    if status == "active":
        status = "under_construction"
    if status not in PROJECT_STATUSES:
        raise ValueError("Status must be planning, under construction, or completed")
    return status


def normalize_type(raw) -> str:
    ptype = (raw or "building").strip().lower().replace(" ", "_")
    if ptype not in PROJECT_TYPES:
        raise ValueError("Project type must be building or housing scheme")
    return ptype


def progress_for_status(status: str, progress) -> int:
    if status == "planning":
        return 0
    if status == "completed":
        return 100
    return max(0, min(100, _int(progress, 0)))


def prepare_project_fields(data: dict, existing: dict | None = None) -> dict:
    """Resolve type, status, progress and floors/units with create-form rules."""
    existing = existing or {}
    status = normalize_status(data["status"] if "status" in data and data["status"] is not None
                              else existing.get("status") or "planning")
    ptype = normalize_type(data["project_type"] if "project_type" in data and data["project_type"] is not None
                           else existing.get("project_type") or "building")
    floors = _int(data["number_of_floors"] if "number_of_floors" in data and data["number_of_floors"] is not None
                  else existing.get("number_of_floors"), 0)
    units = _int(data["number_of_units"] if "number_of_units" in data and data["number_of_units"] is not None
                 else existing.get("number_of_units"), 0)
    if ptype == "housing_scheme":
        floors = 0
    if floors > 0 and units > 0 and floors > units:
        raise ValueError("Planned floors cannot exceed planned units")
    incoming_progress = data["current_progress"] if "current_progress" in data else existing.get("current_progress")
    return {
        "status": status,
        "project_type": ptype,
        "number_of_floors": floors,
        "number_of_units": units,
        "current_progress": progress_for_status(status, incoming_progress),
    }


INVENTORY_SQL = """
    SELECT
        COUNT(*) AS total_units,
        SUM(CASE WHEN status IN ('sold', 'booked', 'possession_delivered') THEN 1 ELSE 0 END) AS sold,
        SUM(CASE WHEN status = 'available' THEN 1 ELSE 0 END) AS available,
        SUM(CASE WHEN status = 'hold' THEN 1 ELSE 0 END) AS hold
    FROM units WHERE project_id=?
"""


def inventory_counts(conn, project_id: int) -> dict:
    row = fetch_one(conn, INVENTORY_SQL, (project_id,))
    return row or {"total_units": 0, "sold": 0, "available": 0, "hold": 0}


def _project_spend(conn, project_id: int) -> dict:
    po = fetch_one(
        conn,
        """SELECT COALESCE(SUM(total),0) AS v FROM purchase_orders
           WHERE project_id=? AND status!='cancelled'""",
        (project_id,),
    )
    paid = fetch_one(
        conn,
        """SELECT COALESCE(SUM(vp.amount),0) AS v
           FROM vendor_payments vp
           JOIN purchase_orders po ON po.id=vp.purchase_order_id
           WHERE po.project_id=? AND po.status!='cancelled'""",
        (project_id,),
    )
    total = po["v"] if po else 0
    vendor_paid = paid["v"] if paid else 0
    return {
        "po_total": total,
        "vendor_paid": vendor_paid,
        "vendor_outstanding": max(total - vendor_paid, 0),
    }


def enrich_project(conn, project: dict) -> dict:
    raw_status = project.get("status", "")
    project["raw_status"] = raw_status
    counts = inventory_counts(conn, project["id"])
    project.update(counts)
    project["total_units"] = counts["total_units"] or project.get("number_of_units", 0)
    project["sold"] = counts["sold"] or 0
    project["available"] = counts["available"] or 0
    project["hold"] = counts["hold"] or 0
    project.update(_project_spend(conn, project["id"]))
    project["progress"] = project.get("current_progress", 0)
    project["end_date"] = project.get("expected_end_date")
    status = project.get("status", "")
    project["status"] = STATUS_LABELS.get(status, status or "—")
    project["project_type_label"] = TYPE_LABELS.get(project.get("project_type") or "building", "Building")
    attrs = project.get("project_attributes") or "[]"
    if isinstance(attrs, str):
        import json
        try:
            project["project_attributes"] = json.loads(attrs)
        except json.JSONDecodeError:
            project["project_attributes"] = []
    return project


def list_projects(conn) -> list[dict]:
    projects = fetch_all(conn, "SELECT * FROM projects ORDER BY id")
    return [enrich_project(conn, p) for p in projects]


def get_project(conn, project_id: int) -> dict | None:
    p = fetch_one(conn, "SELECT * FROM projects WHERE id=?", (project_id,))
    return enrich_project(conn, p) if p else None


def create_project(conn, data: dict) -> dict:
    import json
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("Project name is required")
    fields = prepare_project_fields(data)
    cur = conn.execute(
        """INSERT INTO projects(name, location, description, area, city, start_date,
           expected_end_date, status, project_type, current_progress, number_of_floors, number_of_units,
           project_attributes, total_area_ghaz, estimated_cost)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            name, data.get("location"), data.get("description"),
            data.get("area"), data.get("city"), data.get("start_date"),
            data.get("expected_end_date"), fields["status"], fields["project_type"],
            fields["current_progress"], fields["number_of_floors"],
            fields["number_of_units"],
            json.dumps(data.get("project_attributes") or []),
            data.get("total_area_ghaz"), data.get("estimated_cost"),
        ),
    )
    return get_project(conn, cur.lastrowid)


def delete_project(conn, project_id: int) -> None:
    if not fetch_one(conn, "SELECT id FROM projects WHERE id=?", (project_id,)):
        raise ValueError("Project not found")

    unit_row = fetch_one(
        conn,
        """SELECT COUNT(*) AS total,
                  SUM(CASE WHEN status IN ('sold','booked','possession_delivered') THEN 1 ELSE 0 END) AS locked,
                  SUM(CASE WHEN status NOT IN ('sold','booked','possession_delivered') THEN 1 ELSE 0 END) AS removable
           FROM units WHERE project_id=?""",
        (project_id,),
    )
    total = unit_row["total"] if unit_row else 0
    if total:
        locked = unit_row["locked"] or 0
        removable = unit_row["removable"] or 0
        parts = [f"{total} unit(s) total"]
        if locked:
            parts.append(f"{locked} sold/booked")
        if removable:
            parts.append(f"{removable} can be removed from Unit Inventory")
        raise ValueError(f"Cannot delete project — {' · '.join(parts)}. Delete all units first.")

    po = fetch_one(conn, "SELECT COUNT(*) AS n FROM purchase_orders WHERE project_id=?", (project_id,))
    if po and po["n"]:
        raise ValueError(f"Cannot delete project — {po['n']} purchase order(s) linked. Remove POs first.")

    inv = fetch_one(conn, "SELECT COUNT(*) AS n FROM investor_agreements WHERE project_id=?", (project_id,))
    if inv and inv["n"]:
        raise ValueError(f"Cannot delete project — {inv['n']} investor agreement(s) linked.")

    logs = fetch_one(conn, "SELECT COUNT(*) AS n FROM site_logs WHERE project_id=?", (project_id,))
    if logs and logs["n"]:
        raise ValueError(f"Cannot delete project — {logs['n']} site log(s). Remove them first.")

    conn.execute("DELETE FROM project_budget_lines WHERE project_id=?", (project_id,))
    conn.execute("DELETE FROM projects WHERE id=?", (project_id,))


def update_project(conn, project_id: int, data: dict) -> dict | None:
    import json
    existing = fetch_one(conn, "SELECT * FROM projects WHERE id=?", (project_id,))
    if not existing:
        return None
    resolved = prepare_project_fields(data, existing)
    fields = []
    values = []
    mapping = {
        "name": "name", "location": "location", "description": "description",
        "area": "area", "city": "city", "start_date": "start_date",
        "expected_end_date": "expected_end_date", "total_area_ghaz": "total_area_ghaz",
        "estimated_cost": "estimated_cost",
    }
    for key, col in mapping.items():
        if key in data and data[key] is not None:
            fields.append(f"{col}=?")
            values.append(data[key] if key != "name" else str(data[key]).strip())
    if "name" in data and not str(data.get("name") or "").strip():
        raise ValueError("Project name is required")
    shape = {"status", "project_type", "current_progress", "number_of_floors", "number_of_units"}
    persist = set(shape) & set(data)
    if "status" in data:
        persist.add("current_progress")
    if "project_type" in data:
        persist.add("number_of_floors")
    for key in ("status", "project_type", "current_progress", "number_of_floors", "number_of_units"):
        if key in persist:
            fields.append(f"{key}=?")
            values.append(resolved[key])
    if "project_attributes" in data:
        fields.append("project_attributes=?")
        values.append(json.dumps(data["project_attributes"] or []))
    if not fields:
        return get_project(conn, project_id)
    values.append(project_id)
    conn.execute(f"UPDATE projects SET {', '.join(fields)} WHERE id=?", values)
    if resolved["current_progress"] != (existing.get("current_progress") or 0):
        from backend.services import installment_templates as tmpl_svc
        from datetime import date
        tmpl_svc.activate_milestones_for_project(
            conn, project_id, resolved["current_progress"], date.today().isoformat(),
        )
    return get_project(conn, project_id)
