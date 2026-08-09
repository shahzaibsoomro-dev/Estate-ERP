from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from backend.database import get_db
from backend.services import site_logs as svc
from backend.services.project_filter import parse_project_ids

router = APIRouter(prefix="/api", tags=["site"])


class SiteLogCreate(BaseModel):
    project_id: int
    log_date: str
    engineer: str
    workers_skilled: int = 0
    workers_unskilled: int = 0
    material_used: str | None = None
    work_done: str


def _http(exc: ValueError) -> HTTPException:
    msg = str(exc)
    if "not found" in msg.lower():
        return HTTPException(404, msg)
    return HTTPException(400, msg)


@router.get("/site-logs")
def list_logs(project_id: int | None = Query(None), project_ids: str | None = Query(None)):
    ids = parse_project_ids(project_ids, project_id)
    with get_db() as conn:
        return svc.list_site_logs(conn, ids)


@router.post("/site-logs")
def create_log(body: SiteLogCreate):
    with get_db() as conn:
        try:
            return svc.create_site_log(conn, body.model_dump())
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
