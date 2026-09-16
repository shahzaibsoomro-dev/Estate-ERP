from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from backend.database import get_db
from backend.services import vendors as svc
from backend.services.project_filter import parse_project_ids

router = APIRouter(prefix="/api", tags=["vendors"])


class VendorWrite(BaseModel):
    name: str
    description: str | None = None
    contact: str | None = None
    category: str | None = None
    ntn: str | None = None
    status: str | None = "active"


class POCreate(BaseModel):
    po_no: str | None = None
    vendor_id: int
    project_id: int
    material: str
    total: int | None = None
    qty: str | None = None
    quantity: str | None = None
    unit_cost: int | None = None
    budget_category_id: int | None = None
    category: str | None = None
    site: str | None = None
    order_date: str | None = None
    expected_delivery_date: str | None = None
    notes: str | None = None


class POStatusUpdate(BaseModel):
    status: str


class VendorPaymentCreate(BaseModel):
    vendor_id: int
    purchase_order_id: int | None = None
    amount: int
    payment_date: str | None = None
    payment_method: str = "Bank Transfer"
    reference_number: str | None = None
    notes: str | None = None


def _http(exc: ValueError) -> HTTPException:
    msg = str(exc)
    if "not found" in msg.lower():
        return HTTPException(404, msg)
    return HTTPException(400, msg)


@router.get("/vendors")
def list_vendors():
    with get_db() as conn:
        return svc.list_vendors(conn)


@router.post("/vendors")
def create_vendor(body: VendorWrite):
    with get_db() as conn:
        try:
            return svc.create_vendor(conn, body.model_dump())
        except ValueError as e:
            raise _http(e) from e


@router.get("/vendors/{vendor_id}")
def get_vendor(vendor_id: int):
    with get_db() as conn:
        v = svc.get_vendor(conn, vendor_id)
        if not v:
            raise HTTPException(404, "Vendor not found")
        return v


@router.put("/vendors/{vendor_id}")
def update_vendor(vendor_id: int, body: VendorWrite):
    with get_db() as conn:
        try:
            v = svc.update_vendor(conn, vendor_id, body.model_dump())
        except ValueError as e:
            raise _http(e) from e
    if not v:
        raise HTTPException(404, "Vendor not found")
    return v


@router.delete("/vendors/{vendor_id}")
def delete_vendor(vendor_id: int):
    with get_db() as conn:
        try:
            svc.delete_vendor(conn, vendor_id)
            return {"ok": True}
        except ValueError as e:
            raise _http(e) from e


@router.get("/purchase-orders")
def list_pos(project_id: int | None = Query(None), project_ids: str | None = Query(None)):
    ids = parse_project_ids(project_ids, project_id)
    with get_db() as conn:
        return svc.list_purchase_orders(conn, ids)


@router.get("/purchase-orders/{po_id}")
def get_po(po_id: int):
    with get_db() as conn:
        po = svc.get_purchase_order(conn, po_id)
        if not po:
            raise HTTPException(404, "PO not found")
        return po


@router.post("/purchase-orders")
def create_po(body: POCreate):
    with get_db() as conn:
        try:
            return svc.create_purchase_order(conn, body.model_dump())
        except ValueError as e:
            raise _http(e) from e


@router.put("/purchase-orders/{po_id}/status")
def update_po_status(po_id: int, body: POStatusUpdate):
    with get_db() as conn:
        try:
            po = svc.update_po_status(conn, po_id, body.status)
        except ValueError as e:
            raise _http(e) from e
    if not po:
        raise HTTPException(404, "PO not found")
    return {"ok": True, **po}


@router.post("/vendor-payments")
def vendor_payment(body: VendorPaymentCreate):
    with get_db() as conn:
        try:
            return svc.record_vendor_payment(conn, body.model_dump())
        except ValueError as e:
            raise _http(e) from e
