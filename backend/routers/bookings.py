from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.database import get_db
from backend.services import bookings as svc

router = APIRouter(prefix="/api/bookings", tags=["bookings"])


class InstallmentRow(BaseModel):
    amount: int
    due_date: str
    type: str = "Monthly"
    notes: str | None = None


class CustomerInline(BaseModel):
    name: str
    cnic: str
    phone: str | None = None
    email: str | None = None
    address: str | None = None


class BookingCreate(BaseModel):
    unit_id: int
    project_id: int
    customer_id: int | None = None
    customer: CustomerInline | None = None
    booking_date: str | None = None
    sale_price: int
    base_sale_price: int | None = None
    booking_amount: int | None = None
    down_payment: int | None = None
    possession_date: str | None = None
    agent: str | None = None
    agent_id: int | None = None
    payment_mode: str = "Cheque"
    installments: list[InstallmentRow] = []


class CancelBody(BaseModel):
    reason: str | None = None


@router.get("")
def list_bookings(project_id: int | None = None):
    with get_db() as conn:
        return svc.list_bookings(conn, project_id)


@router.post("")
def create_booking(body: BookingCreate):
    with get_db() as conn:
        try:
            data = body.model_dump()
            data["installments"] = [i.model_dump() if hasattr(i, "model_dump") else i for i in body.installments]
            bk = svc.create_booking(conn, data)
            return {"ok": True, "booking_id": bk["id"]}
        except ValueError as e:
            raise HTTPException(400, str(e)) from e


@router.post("/{booking_id}/cancel")
def cancel_booking(booking_id: int, body: CancelBody | None = None):
    with get_db() as conn:
        try:
            return svc.cancel_booking(conn, booking_id, body.reason if body else None)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
