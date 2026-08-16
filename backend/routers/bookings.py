from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.database import get_db
from backend.services import bookings as svc

router = APIRouter(prefix="/api/bookings", tags=["bookings"])


class InstallmentRow(BaseModel):
    amount: int
    due_date: str | None = None
    type: str = "Monthly"
    notes: str | None = None
    label: str | None = None
    trigger_kind: str | None = None
    trigger_progress: int | None = None
    milestone_progress: int | None = None
    forecast_due_date: str | None = None
    due_days_after_trigger: int | None = None
    trigger_label: str | None = None
    template_rule_id: int | None = None


class CustomerInline(BaseModel):
    name: str
    cnic: str
    phone: str | None = None
    email: str | None = None
    address: str | None = None


class BookingCreate(BaseModel):
    unit_id: int
    project_id: int
    customer_id: int
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
    plan_source: str | None = "custom"
    template_id: int | None = None
    template_revision: int | None = None
    template_name: str | None = None


class PlanPreviewBody(BaseModel):
    project_id: int
    sale_price: int
    booking_amount: int = 0
    template_id: int | None = None


class CancelBody(BaseModel):
    reason: str | None = None


class TransferBody(BaseModel):
    customer_id: int
    notes: str | None = None
    transfer_date: str | None = None


@router.get("")
def list_bookings(project_id: int | None = None):
    with get_db() as conn:
        return svc.list_bookings(conn, project_id)


@router.post("/plan-preview")
def plan_preview(body: PlanPreviewBody):
    from backend.services import installment_templates as tmpl_svc
    with get_db() as conn:
        try:
            return tmpl_svc.preview_plan(
                conn, body.project_id, body.sale_price, body.booking_amount, body.template_id,
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e


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


@router.get("/{booking_id}/cancel-preview")
def cancel_preview(booking_id: int):
    with get_db() as conn:
        try:
            return svc.preview_cancel(conn, booking_id)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e


@router.post("/{booking_id}/cancel")
def cancel_booking(booking_id: int, body: CancelBody | None = None):
    with get_db() as conn:
        try:
            return svc.cancel_booking(conn, booking_id, body.reason if body else None)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e


@router.post("/{booking_id}/transfer")
def transfer_booking(booking_id: int, body: TransferBody):
    with get_db() as conn:
        try:
            return svc.transfer_booking(
                conn, booking_id, body.customer_id, body.notes, body.transfer_date,
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
