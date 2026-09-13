from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from backend.database import get_db
from backend.services import units as svc

router = APIRouter(prefix="/api/units", tags=["units"])


class UnitCreate(BaseModel):
    project_id: int
    unit_no: str
    description: str | None = None
    unit_type: str = "Flat"
    residential_type: str | None = None
    floor_number: int = 1
    area_ghaz: float | None = None
    block_tower: str | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    status: str = "available"
    base_sale_price: int | None = None
    final_sold_price: int | None = None
    booking_amount_required: int | None = None
    furnishing_status: str | None = None
    unit_attributes: list | None = None
    additional_requirements: str | None = None
    possession_date: str | None = None


class StatusUpdate(BaseModel):
    status: str
    hold_customer_id: int | None = None
    hold_until: str | None = None
    hold_notes: str | None = None
    token_amount: int = 0
    payment_method: str | None = None
    method: str | None = None
    bank: str | None = None
    reference_number: str | None = None
    received_by: str | None = None
    receipt_date: str | None = None


class PossessionBody(BaseModel):
    possession_date: str | None = None
    checklist_responses: list[dict] | None = None
    completed_by: str | None = None
    complete_all: bool = False
    skip_checklist: bool = False


class UnitUpdate(BaseModel):
    unit_no: str
    description: str | None = None
    unit_type: str = "Flat"
    residential_type: str | None = None
    floor_number: int = 1
    area_ghaz: float | None = None
    block_tower: str | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    base_sale_price: int | None = None
    booking_amount_required: int | None = None
    furnishing_status: str | None = None
    unit_attributes: list | None = None
    additional_requirements: str | None = None
    possession_date: str | None = None


@router.get("")
def list_units(
    project_id: int | None = Query(None),
    project_ids: str | None = Query(None),
    status: str | None = Query(None),
    floor: int | None = Query(None),
):
    from backend.services.project_filter import parse_project_ids
    ids = parse_project_ids(project_ids, project_id)
    with get_db() as conn:
        return svc.list_units(conn, project_ids=ids, status=status, floor=floor)


@router.get("/{unit_id}")
def get_unit(unit_id: int):
    with get_db() as conn:
        detail = svc.get_unit_detail(conn, unit_id)
        if not detail:
            raise HTTPException(404, "Unit not found")
        return detail


@router.post("")
def create_unit(body: UnitCreate):
    with get_db() as conn:
        try:
            return svc.create_unit(conn, body.model_dump())
        except ValueError as e:
            raise HTTPException(400, str(e)) from e


@router.put("/{unit_id}")
def update_unit(unit_id: int, body: UnitUpdate):
    with get_db() as conn:
        try:
            return svc.update_unit(conn, unit_id, body.model_dump())
        except ValueError as e:
            raise HTTPException(400, str(e)) from e


@router.put("/{unit_id}/status")
def update_status(unit_id: int, body: StatusUpdate):
    with get_db() as conn:
        try:
            u = svc.update_status(
                conn, unit_id, body.status,
                body.hold_customer_id, body.hold_until, body.hold_notes,
                token_amount=body.token_amount,
                payment_method=body.payment_method,
                method=body.method,
                bank=body.bank,
                reference_number=body.reference_number,
                received_by=body.received_by,
                receipt_date=body.receipt_date,
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        if not u:
            raise HTTPException(404, "Unit not found")
        return {"ok": True, "unit": u}


@router.post("/{unit_id}/possession")
def mark_possession(unit_id: int, body: PossessionBody | None = None):
    with get_db() as conn:
        try:
            data = body.model_dump() if body else {}
            return svc.mark_possession(
                conn, unit_id,
                possession_date=data.get("possession_date"),
                checklist_responses=data.get("checklist_responses"),
                completed_by=data.get("completed_by"),
                skip_checklist=bool(data.get("skip_checklist")),
                complete_all=bool(data.get("complete_all")),
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e


@router.delete("/{unit_id}")
def delete_unit(unit_id: int):
    with get_db() as conn:
        try:
            svc.delete_unit(conn, unit_id)
            return {"ok": True}
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
