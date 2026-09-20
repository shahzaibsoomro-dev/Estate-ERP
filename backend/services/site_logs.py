import json
import uuid
from datetime import datetime
from pathlib import Path

from backend.config import DB_PATH
from backend.database import current_db_path, fetch_all, fetch_one
from backend.services.project_filter import sql_in

MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024
ALLOWED_PREFIXES = ("image/", "video/", "audio/")
ALLOWED_TYPES = {
    "application/pdf",
    "text/plain",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _clean(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _fmt_qty(q) -> str:
    if q in (None, ""):
        return ""
    try:
        f = float(q)
        if f == int(f):
            return str(int(f))
        return f"{f:g}"
    except (TypeError, ValueError):
        return str(q)


def _int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value, default=None):
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _hours_worked(data: dict):
    raw = _float(data.get("hours_worked"))
    if raw is not None:
        return max(raw, 0)
    tf, tt = _clean(data.get("time_from")), _clean(data.get("time_to"))
    if not tf or not tt:
        return None
    try:
        a = datetime.strptime(tf[:5], "%H:%M")
        b = datetime.strptime(tt[:5], "%H:%M")
    except ValueError:
        return None
    mins = (b - a).total_seconds() / 60
    if mins < 0:
        mins += 24 * 60
    return round(mins / 60, 2)


def _materials(data: dict) -> tuple[str | None, str | None, list]:
    raw = data.get("materials")
    if raw in (None, "", []):
        raw = data.get("materials_json")
    items = []
    if isinstance(raw, str) and raw.strip():
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            label = _clean(data.get("material_used")) or _clean(raw)
            return label, None, []
    if isinstance(raw, list):
        for it in raw:
            if not isinstance(it, dict):
                continue
            name = _clean(it.get("name") or it.get("material"))
            if not name:
                continue
            items.append({
                "name": name,
                "qty": it.get("qty") if it.get("qty") not in (None, "") else it.get("quantity"),
                "unit": _clean(it.get("unit")),
                "notes": _clean(it.get("notes")),
            })
    label = _clean(data.get("material_used"))
    if items and not label:
        parts = []
        for i in items:
            bit = i["name"]
            qty_s = _fmt_qty(i.get("qty"))
            if qty_s:
                bit += f" {qty_s}"
                if i.get("unit"):
                    bit += f" {i['unit']}"
            parts.append(bit.strip())
        label = ", ".join(parts)
    dumped = json.dumps(items) if items else None
    return label, dumped, items


def _uploads_root() -> Path:
    db = current_db_path.get() or DB_PATH
    root = Path(db).resolve().parent / "uploads" / "site_logs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_filename(name: str) -> str:
    base = Path(name or "file").name
    keep = "".join(c if c.isalnum() or c in "._- " else "_" for c in base)[:80].strip()
    return keep or "file"


def _kind(mime: str | None, filename: str) -> str:
    mime = (mime or "").lower()
    if mime.startswith("image/"):
        return "photo"
    if mime.startswith("video/"):
        return "video"
    ext = Path(filename).suffix.lower()
    if ext in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic"}:
        return "photo"
    if ext in {".mp4", ".mov", ".webm", ".avi", ".mkv"}:
        return "video"
    return "file"


def _public_att(row: dict) -> dict:
    return {
        "id": row["id"],
        "filename": row["filename"],
        "mime": row.get("mime"),
        "size": row.get("size") or 0,
        "kind": row.get("kind") or "file",
        "created_at": row.get("created_at"),
    }


def _with_extras(conn, row: dict) -> dict:
    materials = []
    if row.get("materials_json"):
        try:
            parsed = json.loads(row["materials_json"])
            if isinstance(parsed, list):
                materials = parsed
        except json.JSONDecodeError:
            materials = []
    row["materials"] = materials
    atts = fetch_all(
        conn,
        """SELECT id, filename, mime, size, kind, created_at
           FROM site_log_attachments WHERE site_log_id=? ORDER BY id""",
        (row["id"],),
    )
    row["attachments"] = [_public_att(a) for a in atts]
    return row


def get_site_log(conn, log_id: int) -> dict | None:
    row = fetch_one(
        conn,
        """SELECT sl.*, p.name AS project_name, p.current_progress
           FROM site_logs sl
           JOIN projects p ON p.id=sl.project_id
           WHERE sl.id=?""",
        (log_id,),
    )
    return _with_extras(conn, row) if row else None


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
    return [_with_extras(conn, r) for r in fetch_all(conn, q, tuple(extra))]


def _maybe_progress(conn, project_id: int, progress) -> None:
    if progress is None or progress == "":
        return
    try:
        pct = int(progress)
    except (TypeError, ValueError):
        return
    pct = max(0, min(100, pct))
    conn.execute("UPDATE projects SET current_progress=? WHERE id=?", (pct, project_id))


def _payload(data: dict, existing: dict | None = None) -> dict:
    existing = existing or {}
    project_id = data.get("project_id") or existing.get("project_id")
    log_date = _clean(data.get("log_date")) or existing.get("log_date")
    engineer = _clean(data.get("engineer")) or existing.get("engineer")
    work_done = _clean(data.get("work_done")) or existing.get("work_done")
    if not project_id or not log_date or not engineer or not work_done:
        raise ValueError("Project, date, engineer and work done are required")
    material_used, materials_json, _ = _materials(data)
    if "material_used" not in data and "materials" not in data and "materials_json" not in data:
        material_used = existing.get("material_used")
        materials_json = existing.get("materials_json")
    hours = _hours_worked(data)
    if hours is None and existing:
        hours = existing.get("hours_worked")
    extra_exp = data.get("extra_expenses")
    if extra_exp in (None, "") and existing:
        extra_exp = existing.get("extra_expenses") or 0
    extra_exp = max(_int(extra_exp, 0), 0)
    return {
        "project_id": project_id,
        "log_date": log_date,
        "engineer": engineer,
        "work_done": work_done,
        "workers_skilled": max(_int(data.get("workers_skilled"), existing.get("workers_skilled") or 0), 0),
        "workers_unskilled": max(_int(data.get("workers_unskilled"), existing.get("workers_unskilled") or 0), 0),
        "material_used": material_used,
        "materials_json": materials_json,
        "reporter": _clean(data.get("reporter")) if "reporter" in data else existing.get("reporter"),
        "time_from": _clean(data.get("time_from")) if "time_from" in data else existing.get("time_from"),
        "time_to": _clean(data.get("time_to")) if "time_to" in data else existing.get("time_to"),
        "hours_worked": hours,
        "extra_expenses": extra_exp,
        "expense_notes": _clean(data.get("expense_notes")) if "expense_notes" in data else existing.get("expense_notes"),
        "notes": _clean(data.get("notes")) if "notes" in data else existing.get("notes"),
        "workforce_notes": _clean(data.get("workforce_notes")) if "workforce_notes" in data else existing.get("workforce_notes"),
    }


def create_site_log(conn, data: dict) -> dict:
    payload = _payload(data)
    if not fetch_one(conn, "SELECT id FROM projects WHERE id=?", (payload["project_id"],)):
        raise ValueError("Project not found")
    _maybe_progress(conn, payload["project_id"], data.get("current_progress"))
    if data.get("current_progress") not in (None, ""):
        from backend.services import installment_templates as tmpl_svc
        tmpl_svc.activate_milestones_for_project(
            conn, payload["project_id"], data.get("current_progress"), payload["log_date"],
        )
    cur = conn.execute(
        """INSERT INTO site_logs(
             project_id, log_date, engineer, workers_skilled, workers_unskilled,
             material_used, materials_json, work_done, reporter, time_from, time_to,
             hours_worked, extra_expenses, expense_notes, notes, workforce_notes)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            payload["project_id"], payload["log_date"], payload["engineer"],
            payload["workers_skilled"], payload["workers_unskilled"],
            payload["material_used"], payload["materials_json"], payload["work_done"],
            payload["reporter"], payload["time_from"], payload["time_to"],
            payload["hours_worked"], payload["extra_expenses"], payload["expense_notes"],
            payload["notes"], payload["workforce_notes"],
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
    payload = _payload(data, existing)
    if not fetch_one(conn, "SELECT id FROM projects WHERE id=?", (payload["project_id"],)):
        raise ValueError("Project not found")
    _maybe_progress(conn, payload["project_id"], data.get("current_progress"))
    if data.get("current_progress") not in (None, ""):
        from backend.services import installment_templates as tmpl_svc
        tmpl_svc.activate_milestones_for_project(
            conn, payload["project_id"], data.get("current_progress"), payload["log_date"],
        )
    conn.execute(
        """UPDATE site_logs SET project_id=?, log_date=?, engineer=?, workers_skilled=?,
           workers_unskilled=?, material_used=?, materials_json=?, work_done=?, reporter=?,
           time_from=?, time_to=?, hours_worked=?, extra_expenses=?, expense_notes=?,
           notes=?, workforce_notes=? WHERE id=?""",
        (
            payload["project_id"], payload["log_date"], payload["engineer"],
            payload["workers_skilled"], payload["workers_unskilled"],
            payload["material_used"], payload["materials_json"], payload["work_done"],
            payload["reporter"], payload["time_from"], payload["time_to"],
            payload["hours_worked"], payload["extra_expenses"], payload["expense_notes"],
            payload["notes"], payload["workforce_notes"], log_id,
        ),
    )
    row = get_site_log(conn, log_id)
    if not row:
        raise ValueError("Site log not found")
    return row


def _delete_att_file(stored_name: str | None) -> None:
    if not stored_name:
        return
    path = _uploads_root() / stored_name
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def delete_site_log(conn, log_id: int) -> None:
    if not fetch_one(conn, "SELECT id FROM site_logs WHERE id=?", (log_id,)):
        raise ValueError("Site log not found")
    atts = fetch_all(conn, "SELECT stored_name FROM site_log_attachments WHERE site_log_id=?", (log_id,))
    for a in atts:
        _delete_att_file(a.get("stored_name"))
    conn.execute("DELETE FROM site_log_attachments WHERE site_log_id=?", (log_id,))
    conn.execute("DELETE FROM site_logs WHERE id=?", (log_id,))


def add_attachments(conn, log_id: int, files: list) -> dict:
    row = fetch_one(conn, "SELECT id FROM site_logs WHERE id=?", (log_id,))
    if not row:
        raise ValueError("Site log not found")
    for f in files or []:
        if isinstance(f, dict):
            filename = _safe_filename(f.get("filename") or "file")
            mime = f.get("content_type") or f.get("mime") or "application/octet-stream"
            data = f.get("data") or b""
        else:
            filename = _safe_filename(getattr(f, "filename", None) or "file")
            mime = getattr(f, "content_type", None) or "application/octet-stream"
            data = f.file.read() if hasattr(f, "file") else f.read()
        if not data:
            continue
        if not (mime.startswith(ALLOWED_PREFIXES) or mime in ALLOWED_TYPES or mime == "application/octet-stream"):
            raise ValueError(f"File type not allowed: {filename}")
        if len(data) > MAX_ATTACHMENT_BYTES:
            raise ValueError(f"{filename} is larger than 25 MB")
        stored = f"{log_id}_{uuid.uuid4().hex}_{filename}"
        dest = _uploads_root() / stored
        dest.write_bytes(data)
        kind = _kind(mime, filename)
        conn.execute(
            """INSERT INTO site_log_attachments(site_log_id, filename, stored_name, mime, size, kind)
               VALUES(?,?,?,?,?,?)""",
            (log_id, filename, stored, mime, len(data), kind),
        )
    return get_site_log(conn, log_id)


def attachment_path(conn, log_id: int, att_id: int) -> tuple[Path, dict]:
    att = fetch_one(
        conn,
        """SELECT * FROM site_log_attachments WHERE id=? AND site_log_id=?""",
        (att_id, log_id),
    )
    if not att:
        raise ValueError("Attachment not found")
    path = _uploads_root() / att["stored_name"]
    if not path.is_file():
        raise ValueError("Attachment file missing")
    return path, att


def delete_attachment(conn, log_id: int, att_id: int) -> dict:
    att = fetch_one(
        conn,
        "SELECT * FROM site_log_attachments WHERE id=? AND site_log_id=?",
        (att_id, log_id),
    )
    if not att:
        raise ValueError("Attachment not found")
    _delete_att_file(att.get("stored_name"))
    conn.execute("DELETE FROM site_log_attachments WHERE id=?", (att_id,))
    return get_site_log(conn, log_id)
