from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.database import get_db
from backend.services import possession as svc

router = APIRouter(prefix="/api/possession", tags=["possession"])


class TemplateWrite(BaseModel):
    name: str
    is_default: bool = False
    items: list[dict | str]


class ResponseItem(BaseModel):
    id: int
    checked: bool = False
    notes: str | None = None


class ChecklistUpdate(BaseModel):
    responses: list[ResponseItem] = []
    notes: str | None = None
    completed_by: str | None = None


class StartBody(BaseModel):
    possession_date: str | None = None
    template_id: int | None = None
    completed_by: str | None = None


class CompleteBody(BaseModel):
    completed_by: str | None = None
    force: bool = False


def _http(exc: ValueError) -> HTTPException:
    msg = str(exc)
    if "not found" in msg.lower():
        return HTTPException(404, msg)
    return HTTPException(400, msg)


@router.get("/templates")
def list_templates():
    with get_db() as conn:
        return svc.list_templates(conn)


@router.post("/templates")
def create_template(body: TemplateWrite):
    with get_db() as conn:
        try:
            return svc.save_template(conn, body.model_dump())
        except ValueError as e:
            raise _http(e) from e


@router.put("/templates/{template_id}")
def update_template(template_id: int, body: TemplateWrite):
    with get_db() as conn:
        try:
            return svc.save_template(conn, body.model_dump(), template_id=template_id)
        except ValueError as e:
            raise _http(e) from e


@router.get("/checklists/{checklist_id}")
def get_checklist(checklist_id: int):
    with get_db() as conn:
        row = svc.get_checklist(conn, checklist_id)
        if not row:
            raise HTTPException(404, "Checklist not found")
        return row


@router.get("/units/{unit_id}/checklist")
def unit_checklist(unit_id: int):
    with get_db() as conn:
        row = svc.get_checklist_for_unit(conn, unit_id)
        if not row:
            raise HTTPException(404, "No checklist for this unit")
        return row


@router.post("/units/{unit_id}/checklist")
def start_checklist(unit_id: int, body: StartBody):
    with get_db() as conn:
        try:
            return svc.start_checklist(
                conn, unit_id, body.possession_date, body.template_id, body.completed_by,
            )
        except ValueError as e:
            raise _http(e) from e


@router.put("/checklists/{checklist_id}")
def update_checklist(checklist_id: int, body: ChecklistUpdate):
    with get_db() as conn:
        try:
            return svc.update_responses(
                conn, checklist_id,
                [r.model_dump() for r in body.responses],
                body.notes, body.completed_by,
            )
        except ValueError as e:
            raise _http(e) from e


@router.post("/checklists/{checklist_id}/complete")
def complete_checklist(checklist_id: int, body: CompleteBody):
    with get_db() as conn:
        try:
            return svc.complete_checklist(conn, checklist_id, body.completed_by, body.force)
        except ValueError as e:
            raise _http(e) from e
