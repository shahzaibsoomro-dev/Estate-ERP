from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.database import get_db
from backend.services import payments as svc

router = APIRouter(prefix="/api/payments", tags=["payments"])


class PaymentCreate(BaseModel):
    installment_id: int | None = None
    booking_id: int
    customer_id: int
    amount: int
    paid_date: str | None = None
    payment_date: str | None = None
    method: str = "Cash"
    payment_method: str | None = None
    bank: str | None = None
    reference_number: str | None = None
    received_by: str | None = None
    notes: str | None = None


@router.post("")
def record_payment(body: PaymentCreate):
    with get_db() as conn:
        try:
            return svc.record_payment(conn, body.model_dump())
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
