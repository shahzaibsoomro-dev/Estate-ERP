from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.database import get_db
from backend.services import planning as svc
from backend.services.project_filter import parse_project_ids

router = APIRouter(prefix="/api/planning", tags=["planning"])


class StageWrite(BaseModel):
    project_id: int | None = None
    name: str | None = None
    weight_bps: int | None = None
    planned_start: str | None = None
    planned_end: str | None = None
    actual_start: str | None = None
    actual_end: str | None = None
    status: str | None = None
    sort_order: int | None = None
    notes: str | None = None


class TaskWrite(BaseModel):
    stage_id: int | None = None
    name: str | None = None
    planned_start: str | None = None
    planned_end: str | None = None
    weight_bps: int | None = None
    progress_pct: int | None = None
    depends_on_task_id: int | None = None
    lag_days: int | None = None
    workers_skilled: int | None = None
    workers_unskilled: int | None = None
    skilled_rate: int | None = None
    unskilled_rate: int | None = None
    status: str | None = None
    sort_order: int | None = None
    notes: str | None = None


class MoveBody(BaseModel):
    planned_start: str | None = None
    planned_end: str | None = None
    keep_duration: bool = False


class ProgressBody(BaseModel):
    progress_pct: int


class ModeBody(BaseModel):
    project_id: int
    progress_mode: str


class ReorderBody(BaseModel):
    project_id: int
    stage_ids: list[int]


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


def _one_project(project_id: int | None, project_ids: str | None) -> int:
    """Scoped employees have their project_id rewritten to project_ids by the middleware."""
    ids = parse_project_ids(project_ids)
    pid = project_id or (ids[0] if ids else None)
    if not pid:
        raise HTTPException(400, "project_id is required")
    return int(pid)


@router.get("/overview")
def overview(project_id: int | None = Query(None), project_ids: str | None = Query(None)):
    with get_db() as conn:
        return _guard(svc.overview, conn, _one_project(project_id, project_ids))


@router.get("/stage-hints")
def stage_hints(project_id: int | None = Query(None), project_ids: str | None = Query(None)):
    with get_db() as conn:
        return _guard(svc.stage_progress_hints, conn, _one_project(project_id, project_ids))


@router.post("/stages")
def create_stage(body: StageWrite):
    with get_db() as conn:
        return _guard(svc.create_stage, conn, body.model_dump(exclude_unset=True))


@router.put("/stages/{stage_id}")
def update_stage(stage_id: int, body: StageWrite):
    with get_db() as conn:
        return _guard(svc.update_stage, conn, stage_id, body.model_dump(exclude_unset=True))


@router.delete("/stages/{stage_id}")
def delete_stage(stage_id: int):
    with get_db() as conn:
        _guard(svc.delete_stage, conn, stage_id)
        return {"ok": True}


@router.post("/stages/{stage_id}/even-task-weights")
def even_task_weights(stage_id: int):
    with get_db() as conn:
        return _guard(svc.even_task_weights, conn, stage_id)


@router.post("/stages/reorder")
def reorder_stages(body: ReorderBody):
    with get_db() as conn:
        return _guard(svc.reorder_stages, conn, body.project_id, body.stage_ids)


@router.post("/even-stage-weights")
def even_stage_weights(project_id: int = Query(...)):
    with get_db() as conn:
        return _guard(svc.even_stage_weights, conn, project_id)


@router.post("/tasks")
def create_task(body: TaskWrite):
    with get_db() as conn:
        return _guard(svc.create_task, conn, body.model_dump(exclude_unset=True))


@router.put("/tasks/{task_id}")
def update_task(task_id: int, body: TaskWrite):
    with get_db() as conn:
        return _guard(svc.update_task, conn, task_id, body.model_dump(exclude_unset=True))


@router.delete("/tasks/{task_id}")
def delete_task(task_id: int):
    with get_db() as conn:
        _guard(svc.delete_task, conn, task_id)
        return {"ok": True}


@router.post("/tasks/{task_id}/move")
def move_task(task_id: int, body: MoveBody):
    with get_db() as conn:
        return _guard(svc.move_task, conn, task_id, body.planned_start, body.planned_end, body.keep_duration)


@router.post("/tasks/{task_id}/progress")
def set_task_progress(task_id: int, body: ProgressBody):
    with get_db() as conn:
        return _guard(svc.set_task_progress, conn, task_id, body.progress_pct)


@router.post("/recompute")
def recompute(project_id: int = Query(...)):
    with get_db() as conn:
        return _guard(svc.recompute_progress, conn, project_id)


@router.post("/progress-mode")
def progress_mode(body: ModeBody):
    with get_db() as conn:
        return _guard(svc.set_progress_mode, conn, body.project_id, body.progress_mode)
