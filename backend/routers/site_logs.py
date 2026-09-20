from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.database import get_db
from backend.services import site_logs as svc
from backend.services.project_filter import parse_project_ids

router = APIRouter(prefix="/api", tags=["site"])


class MaterialLine(BaseModel):
    name: str
    qty: float | str | None = None
    quantity: float | str | None = None
    unit: str | None = None
    notes: str | None = None


class SiteLogCreate(BaseModel):
    project_id: int
    log_date: str
    engineer: str
    workers_skilled: int = 0
    workers_unskilled: int = 0
    material_used: str | None = None
    materials: list[MaterialLine] | None = None
    work_done: str
    current_progress: int | None = None
    reporter: str | None = None
    time_from: str | None = None
    time_to: str | None = None
    hours_worked: float | None = None
    extra_expenses: int | None = 0
    expense_notes: str | None = None
    notes: str | None = None
    workforce_notes: str | None = None


class SiteLogUpdate(BaseModel):
    project_id: int | None = None
    log_date: str | None = None
    engineer: str | None = None
    workers_skilled: int | None = None
    workers_unskilled: int | None = None
    material_used: str | None = None
    materials: list[MaterialLine] | None = None
    work_done: str | None = None
    current_progress: int | None = None
    reporter: str | None = None
    time_from: str | None = None
    time_to: str | None = None
    hours_worked: float | None = None
    extra_expenses: int | None = None
    expense_notes: str | None = None
    notes: str | None = None
    workforce_notes: str | None = None


def _http(exc: ValueError) -> HTTPException:
    msg = str(exc)
    if "not found" in msg.lower():
        return HTTPException(404, msg)
    return HTTPException(400, msg)


def _dump(body: BaseModel, *, partial: bool = False) -> dict:
    data = body.model_dump(exclude_unset=partial)
    mats = data.get("materials")
    if mats is not None:
        data["materials"] = [m if isinstance(m, dict) else m for m in mats]
    return data


@router.get("/site-logs")
def list_logs(
    project_id: int | None = Query(None),
    project_ids: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
):
    ids = parse_project_ids(project_ids, project_id)
    with get_db() as conn:
        return svc.list_site_logs(conn, ids, date_from, date_to)


@router.get("/site-logs/{log_id}")
def get_log(log_id: int):
    with get_db() as conn:
        row = svc.get_site_log(conn, log_id)
    if not row:
        raise HTTPException(404, "Site log not found")
    return row


@router.post("/site-logs")
def create_log(body: SiteLogCreate):
    with get_db() as conn:
        try:
            return svc.create_site_log(conn, _dump(body))
        except ValueError as e:
            raise _http(e) from e


@router.put("/site-logs/{log_id}")
def update_log(log_id: int, body: SiteLogUpdate):
    with get_db() as conn:
        try:
            return svc.update_site_log(conn, log_id, _dump(body, partial=True))
        except ValueError as e:
            raise _http(e) from e


@router.delete("/site-logs/{log_id}")
def delete_log(log_id: int):
    with get_db() as conn:
        try:
            svc.delete_site_log(conn, log_id)
            return {"ok": True}
        except ValueError as e:
            raise _http(e) from e


@router.post("/site-logs/{log_id}/attachments")
async def upload_attachments(log_id: int, files: list[UploadFile] = File(...)):
    blobs = []
    for f in files:
        blobs.append({
            "filename": f.filename,
            "content_type": f.content_type,
            "data": await f.read(),
        })
    with get_db() as conn:
        try:
            return svc.add_attachments(conn, log_id, blobs)
        except ValueError as e:
            raise _http(e) from e


@router.get("/site-logs/{log_id}/attachments/{att_id}")
def download_attachment(log_id: int, att_id: int):
    with get_db() as conn:
        try:
            path, att = svc.attachment_path(conn, log_id, att_id)
        except ValueError as e:
            raise _http(e) from e
    return FileResponse(Path(path), filename=att["filename"], media_type=att.get("mime") or "application/octet-stream")


@router.delete("/site-logs/{log_id}/attachments/{att_id}")
def delete_attachment(log_id: int, att_id: int):
    with get_db() as conn:
        try:
            return svc.delete_attachment(conn, log_id, att_id)
        except ValueError as e:
            raise _http(e) from e
