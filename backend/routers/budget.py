from fastapi import APIRouter, Query
from pydantic import BaseModel
from backend.database import get_db
from backend.services import budget as svc

router = APIRouter(prefix="/api/budget", tags=["budget"])


class CategoryCreate(BaseModel):
    name: str
    sort_order: int = 0


class LineCreate(BaseModel):
    project_id: int
    category_id: int
    planned_amount: int
    revision_no: int = 1
    notes: str | None = None


class ReviseBody(BaseModel):
    planned_amount: int
    notes: str | None = None


@router.get("/categories")
def list_categories():
    with get_db() as conn:
        return svc.list_categories(conn)


@router.post("/categories")
def create_category(body: CategoryCreate):
    with get_db() as conn:
        return svc.create_category(conn, body.name, body.sort_order)


@router.delete("/categories/{category_id}")
def delete_category(category_id: int):
    with get_db() as conn:
        try:
            svc.delete_category(conn, category_id)
            return {"ok": True}
        except ValueError as e:
            from fastapi import HTTPException
            raise HTTPException(400, str(e)) from e


@router.get("/lines")
def list_lines(project_id: int | None = Query(None)):
    with get_db() as conn:
        return svc.list_lines(conn, project_id)


@router.post("/lines")
def create_line(body: LineCreate):
    with get_db() as conn:
        return svc.create_line(conn, body.model_dump())


@router.post("/lines/{line_id}/revise")
def revise_line(line_id: int, body: ReviseBody):
    with get_db() as conn:
        try:
            return svc.revise_line(conn, line_id, body.planned_amount, body.notes)
        except ValueError as e:
            from fastapi import HTTPException
            raise HTTPException(400, str(e)) from e


@router.get("/summary")
def budget_summary(project_id: int | None = Query(None)):
    with get_db() as conn:
        return svc.summary(conn, project_id)
