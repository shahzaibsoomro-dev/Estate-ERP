from backend.database import fetch_all, fetch_one
from backend.services.project_filter import sql_in


def _clean(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def get_site_log(conn, log_id: int) -> dict | None:
    return fetch_one(
        conn,
        """SELECT sl.*, p.name AS project_name, p.current_progress
           FROM site_logs sl
           JOIN projects p ON p.id=sl.project_id
           WHERE sl.id=?""",
        (log_id,),
    )


def list_site_logs(
    conn,
    project_ids: list[int] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    q = """SELECT sl.*, p.name AS project_name, p.current_progress
           FROM site_logs sl
           JOIN projects p ON p.id=sl.project_id
           WHERE 1=1"""
    clause, params = sql_in("sl.project_id", project_ids)
    q += clause
    extra: list = list(params)
    if date_from:
        q += " AND sl.log_date>=?"
        extra.append(date_from)
    if date_to:
        q += " AND sl.log_date<=?"
        extra.append(date_to)
    q += " ORDER BY sl.log_date DESC, sl.id DESC"
    return fetch_all(conn, q, tuple(extra))


def _maybe_progress(conn, project_id: int, progress) -> None:
    if progress is None or progress == "":
        return
    try:
        pct = int(progress)
    except (TypeError, ValueError):
        return
    pct = max(0, min(100, pct))
    conn.execute("UPDATE projects SET current_progress=? WHERE id=?", (pct, project_id))


def create_site_log(conn, data: dict) -> dict:
    project_id = data.get("project_id")
    log_date = _clean(data.get("log_date"))
    engineer = _clean(data.get("engineer"))
    work_done = _clean(data.get("work_done"))
    if not project_id or not log_date or not engineer or not work_done:
        raise ValueError("Project, date, engineer and work done are required")
    if not fetch_one(conn, "SELECT id FROM projects WHERE id=?", (project_id,)):
        raise ValueError("Project not found")
    _maybe_progress(conn, project_id, data.get("current_progress"))
    if data.get("current_progress") not in (None, ""):
        from backend.services import installment_templates as tmpl_svc
        tmpl_svc.activate_milestones_for_project(
            conn, project_id, data.get("current_progress"), log_date,
        )
    cur = conn.execute(
        """INSERT INTO site_logs(project_id, log_date, engineer, workers_skilled,
           workers_unskilled, material_used, work_done)
           VALUES(?,?,?,?,?,?,?)""",
        (
            project_id, log_date, engineer,
            max(_int(data.get("workers_skilled")), 0),
            max(_int(data.get("workers_unskilled")), 0),
            _clean(data.get("material_used")), work_done,
        ),
    )
    row = get_site_log(conn, cur.lastrowid)
    if not row:
        raise ValueError("Failed to save site log")
    return row


def update_site_log(conn, log_id: int, data: dict) -> dict:
    existing = fetch_one(conn, "SELECT * FROM site_logs WHERE id=?", (log_id,))
    if not existing:
        raise ValueError("Site log not found")
    project_id = data.get("project_id") or existing["project_id"]
    log_date = _clean(data.get("log_date")) or existing["log_date"]
    engineer = _clean(data.get("engineer")) or existing["engineer"]
    work_done = _clean(data.get("work_done")) or existing["work_done"]
    if not fetch_one(conn, "SELECT id FROM projects WHERE id=?", (project_id,)):
        raise ValueError("Project not found")
    _maybe_progress(conn, project_id, data.get("current_progress"))
    if data.get("current_progress") not in (None, ""):
        from backend.services import installment_templates as tmpl_svc
        tmpl_svc.activate_milestones_for_project(
            conn, project_id, data.get("current_progress"),
            _clean(data.get("log_date")) or existing["log_date"],
        )
    conn.execute(
        """UPDATE site_logs SET project_id=?, log_date=?, engineer=?, workers_skilled=?,
           workers_unskilled=?, material_used=?, work_done=? WHERE id=?""",
        (
            project_id, log_date, engineer,
            max(_int(data.get("workers_skilled"), existing["workers_skilled"]), 0),
            max(_int(data.get("workers_unskilled"), existing["workers_unskilled"]), 0),
            _clean(data.get("material_used")) if "material_used" in data else existing["material_used"],
            work_done, log_id,
        ),
    )
    row = get_site_log(conn, log_id)
    if not row:
        raise ValueError("Site log not found")
    return row


def delete_site_log(conn, log_id: int) -> None:
    if not fetch_one(conn, "SELECT id FROM site_logs WHERE id=?", (log_id,)):
        raise ValueError("Site log not found")
    conn.execute("DELETE FROM site_logs WHERE id=?", (log_id,))
