from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.database import get_db
from backend.services import customers as svc

router = APIRouter(prefix="/api/customers", tags=["customers"])


class CustomerCreate(BaseModel):
    name: str
    cnic: str
    father_name: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    emergency_contact_number: str | None = None


@router.get("")
def list_customers():
    with get_db() as conn:
        return svc.list_customers(conn)


@router.get("/{customer_id}")
def get_customer(customer_id: int):
    with get_db() as conn:
        c = svc.get_customer(conn, customer_id)
        if not c:
            raise HTTPException(404, "Customer not found")
        return c


@router.post("")
def create_customer(body: CustomerCreate):
    with get_db() as conn:
        try:
            c = svc.create_customer(conn, body.model_dump())
            return {"ok": True, "id": c["id"], **c}
        except Exception as e:
            if "UNIQUE" in str(e):
                raise HTTPException(400, "CNIC already exists") from e
            raise
