from backend.database import fetch_all, fetch_one


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


def enrich_project(conn, project: dict) -> dict:
    counts = inventory_counts(conn, project["id"])
    project.update(counts)
    project["total_units"] = counts["total_units"] or project.get("number_of_units", 0)
    project["sold"] = counts["sold"] or 0
    project["available"] = counts["available"] or 0
    project["hold"] = counts["hold"] or 0
    project["progress"] = project.get("current_progress", 0)
    project["end_date"] = project.get("expected_end_date")
    status = project.get("status", "")
    if status == "completed":
        project["status"] = "Completed"
    elif status in ("under_construction", "planning"):
        project["status"] = "Active"
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
    cur = conn.execute(
        """INSERT INTO projects(name, location, description, area, city, start_date,
           expected_end_date, status, current_progress, number_of_floors, number_of_units,
           project_attributes, total_area_ghaz, estimated_cost)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            data["name"], data.get("location"), data.get("description"),
            data.get("area"), data.get("city"), data.get("start_date"),
            data.get("expected_end_date"), data.get("status", "planning"),
            data.get("current_progress", 0), data.get("number_of_floors", 0),
            data.get("number_of_units", 0),
            json.dumps(data.get("project_attributes") or []),
            data.get("total_area_ghaz"), data.get("estimated_cost"),
        ),
    )
    return get_project(conn, cur.lastrowid)


def update_project(conn, project_id: int, data: dict) -> dict | None:
    import json
    existing = fetch_one(conn, "SELECT id FROM projects WHERE id=?", (project_id,))
    if not existing:
        return None
    fields = []
    values = []
    mapping = {
        "name": "name", "location": "location", "description": "description",
        "area": "area", "city": "city", "start_date": "start_date",
        "expected_end_date": "expected_end_date", "status": "status",
        "current_progress": "current_progress", "number_of_floors": "number_of_floors",
        "number_of_units": "number_of_units", "total_area_ghaz": "total_area_ghaz",
        "estimated_cost": "estimated_cost",
    }
    for key, col in mapping.items():
        if key in data and data[key] is not None:
            fields.append(f"{col}=?")
            values.append(data[key])
    if "project_attributes" in data:
        fields.append("project_attributes=?")
        values.append(json.dumps(data["project_attributes"] or []))
    if not fields:
        return get_project(conn, project_id)
    values.append(project_id)
    conn.execute(f"UPDATE projects SET {', '.join(fields)} WHERE id=?", values)
    return get_project(conn, project_id)
