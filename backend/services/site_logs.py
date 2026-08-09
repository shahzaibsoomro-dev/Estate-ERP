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


def list_site_logs(conn, project_ids: list[int] | None = None) -> list[dict]:
    q = """SELECT sl.*, p.name AS project_name, p.current_progress
           FROM site_logs sl
           JOIN projects p ON p.id=sl.project_id
           WHERE 1=1"""
    clause, params = sql_in("sl.project_id", project_ids)
    q += clause + " ORDER BY sl.log_date DESC, sl.id DESC"
    return fetch_all(conn, q, params)


def create_site_log(conn, data: dict) -> dict:
    project_id = data.get("project_id")
    log_date = _clean(data.get("log_date"))
    engineer = _clean(data.get("engineer"))
    work_done = _clean(data.get("work_done"))
    if not project_id or not log_date or not engineer or not work_done:
        raise ValueError("Project, date, engineer and work done are required")
    if not fetch_one(conn, "SELECT id FROM projects WHERE id=?", (project_id,)):
        raise ValueError("Project not found")
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


def delete_site_log(conn, log_id: int) -> None:
    if not fetch_one(conn, "SELECT id FROM site_logs WHERE id=?", (log_id,)):
        raise ValueError("Site log not found")
    conn.execute("DELETE FROM site_logs WHERE id=?", (log_id,))
