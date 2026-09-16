from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.database import get_db
from backend.services import holds as svc

router = APIRouter(tags=["holds"])


class HoldCreate(BaseModel):
    customer_id: int | None = None
    hold_customer_id: int | None = None
    hold_until: str | None = None
    notes: str | None = None
    hold_notes: str | None = None
    token_amount: int = 0
    token: int | None = None
    receipt_date: str | None = None
    held_at: str | None = None
    payment_method: str | None = None
    method: str | None = None
    bank: str | None = None
    reference_number: str | None = None
    received_by: str | None = None


class HoldRelease(BaseModel):
    reason: str | None = None


@router.post("/api/units/{unit_id}/holds")
def create_hold(unit_id: int, body: HoldCreate):
    with get_db() as conn:
        try:
            return svc.create_hold(conn, unit_id, body.model_dump())
        except ValueError as e:
            raise HTTPException(400, str(e)) from e


@router.get("/api/units/{unit_id}/holds")
def list_unit_holds(unit_id: int):
    with get_db() as conn:
        svc.expire_due_holds(conn, unit_id=unit_id)
        return {
            "active": svc.get_active_hold(conn, unit_id),
            "history": svc.hold_history(conn, unit_id),
        }


@router.get("/api/holds/{hold_id}")
def get_hold(hold_id: int):
    with get_db() as conn:
        try:
            return svc.hold_detail(conn, hold_id)
        except ValueError as e:
            raise HTTPException(404, str(e)) from e


@router.post("/api/holds/{hold_id}/release")
def release_hold(hold_id: int, body: HoldRelease | None = None):
    with get_db() as conn:
        try:
            return svc.release_hold(conn, hold_id, body.reason if body else None)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e


@router.post("/api/holds/expire-due")
def expire_due():
    with get_db() as conn:
        return {"expired": svc.expire_due_holds(conn)}
