from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.database import get_db
from backend.services import boq as svc
from backend.services.project_filter import parse_project_ids

router = APIRouter(prefix="/api/boq", tags=["boq"])


class LineWrite(BaseModel):
    project_id: int | None = None
    stage_id: int | None = None
    task_id: int | None = None
    item_id: int | None = None
    category_id: int | None = None
    name: str | None = None
    unit: str | None = None
    qty: float | None = None
    wastage_pct: float | None = None
    rate: int | None = None
    notes: str | None = None


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/lines")
def list_lines(project_id: int | None = Query(None), project_ids: str | None = Query(None)):
    ids = parse_project_ids(project_ids)
    with get_db() as conn:
        return svc.list_lines(conn, project_id, ids)


@router.get("/summary")
def summary(project_id: int | None = Query(None), project_ids: str | None = Query(None)):
    ids = parse_project_ids(project_ids)
    pid = project_id or (ids[0] if ids else None)
    if not pid:
        raise HTTPException(400, "project_id is required")
    with get_db() as conn:
        return _guard(svc.summary, conn, int(pid))


@router.post("/lines")
def create_line(body: LineWrite):
    with get_db() as conn:
        return _guard(svc.create_line, conn, body.model_dump(exclude_unset=True))


@router.put("/lines/{line_id}")
def update_line(line_id: int, body: LineWrite):
    with get_db() as conn:
        return _guard(svc.update_line, conn, line_id, body.model_dump(exclude_unset=True))


@router.delete("/lines/{line_id}")
def delete_line(line_id: int):
    with get_db() as conn:
        _guard(svc.delete_line, conn, line_id)
        return {"ok": True}
