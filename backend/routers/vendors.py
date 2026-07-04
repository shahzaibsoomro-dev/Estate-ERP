from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.database import get_db
from backend.services import vendors as svc

router = APIRouter(prefix="/api", tags=["vendors"])


class VendorCreate(BaseModel):
    name: str
    description: str | None = None
    contact: str | None = None
    category: str | None = None


class POCreate(BaseModel):
    po_no: str
    vendor_id: int
    project_id: int
    material: str
    total: int
    qty: str | None = None
    quantity: str | None = None
    unit_cost: int | None = None
    budget_category_id: int | None = None
    category: str | None = None
    site: str | None = None
    order_date: str | None = None
    status: str | None = None
    grn_status: str | None = None


class POStatusUpdate(BaseModel):
    status: str


class VendorPaymentCreate(BaseModel):
    vendor_id: int
    purchase_order_id: int | None = None
    amount: int
    payment_date: str
    payment_method: str = "Bank Transfer"
    reference_number: str | None = None
    notes: str | None = None


@router.get("/vendors")
def list_vendors():
    with get_db() as conn:
        return svc.list_vendors(conn)


@router.post("/vendors")
def create_vendor(body: VendorCreate):
    with get_db() as conn:
        return svc.create_vendor(conn, body.model_dump())


@router.get("/purchase-orders")
def list_pos():
    with get_db() as conn:
        return svc.list_purchase_orders(conn)


@router.post("/purchase-orders")
def create_po(body: POCreate):
    with get_db() as conn:
        svc.create_purchase_order(conn, body.model_dump())
        return {"ok": True}


@router.put("/purchase-orders/{po_id}/status")
def update_po_status(po_id: int, body: POStatusUpdate):
    with get_db() as conn:
        po = svc.update_po_status(conn, po_id, body.status)
        if not po:
            raise HTTPException(404, "PO not found")
        return {"ok": True}


@router.post("/vendor-payments")
def vendor_payment(body: VendorPaymentCreate):
    with get_db() as conn:
        return svc.record_vendor_payment(conn, body.model_dump())
