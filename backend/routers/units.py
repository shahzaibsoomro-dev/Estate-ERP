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
        u = svc.update_status(
            conn, unit_id, body.status,
            body.hold_customer_id, body.hold_until, body.hold_notes,
        )
        if not u:
            raise HTTPException(404, "Unit not found")
        return {"ok": True, "unit": u}


@router.delete("/{unit_id}")
def delete_unit(unit_id: int):
    with get_db() as conn:
        try:
            svc.delete_unit(conn, unit_id)
            return {"ok": True}
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
