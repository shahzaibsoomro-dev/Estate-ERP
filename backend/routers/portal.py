from fastapi import APIRouter, HTTPException, Query
from backend.database import get_db
from backend.services import portal as svc

router = APIRouter(prefix="/api/portal", tags=["portal"])


@router.get("")
def portal(customer_id: int | None = Query(None)):
    with get_db() as conn:
        if customer_id is None:
            return svc.list_portal_customers(conn)
        data = svc.get_portal(conn, customer_id)
        if not data:
            raise HTTPException(404, "Customer not found")
        return data
