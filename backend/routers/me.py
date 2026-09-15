"""Customer self-service. Every query is scoped to the signed-in customer's own id."""
from fastapi import APIRouter, Depends, HTTPException, Request

from backend.auth.deps import require_customer
from backend.database import get_db
from backend.documents import service as docs
from backend.services import portal as portal_svc

router = APIRouter(prefix="/api/me", tags=["customer-portal"], dependencies=[Depends(require_customer)])


def _cid(request: Request) -> int:
    cid = request.state.user.get("customer_id")
    if not request.state.session.get("company"):
        raise HTTPException(403, "No company is linked to this login")
    if not cid:
        raise HTTPException(403, "No customer profile is linked to this login")
    return cid


@router.get("/overview")
def overview(request: Request):
    with get_db() as conn:
        data = portal_svc.get_portal(conn, _cid(request))
        if not data:
            raise HTTPException(404, "Customer profile not found")
        c = data["customer"]
        # Next-of-kin details are not needed in the customer UI.
        data["customer"] = {k: c.get(k) for k in ("name", "father_name", "cnic", "phone", "email", "address")}
        for b in data["bookings"]:
            b.pop("unit_id", None)
            unit = b.get("unit") or {}
            b["unit"] = {k: unit.get(k) for k in ("unit_no", "unit_type", "residential_type", "floor_number",
                                                  "area_ghaz", "block_tower", "bedrooms", "bathrooms")}
        return data


@router.get("/documents")
def my_documents(request: Request):
    with get_db() as conn:
        return docs.list_documents(conn, _cid(request), customer_view=True)
