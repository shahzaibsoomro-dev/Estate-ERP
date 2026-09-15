"""Customer (owner) portal logins for the current company."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from backend.auth import service
from backend.auth.deps import company_id, require_company_staff
from backend.database import fetch_all, fetch_one, get_db, platform_db

router = APIRouter(prefix="/api/portal-access", tags=["portal-access"], dependencies=[Depends(require_company_staff)])


class EnableBody(BaseModel):
    customer_id: int
    email: str | None = Field(None, max_length=254)


class StatusBody(BaseModel):
    is_active: bool


def _customer_user(conn, user_id: int, cid: int) -> dict:
    u = service.get_user(conn, user_id)
    if not u or u["role"] != "customer" or u["company_id"] != cid:
        raise HTTPException(404, "Customer login not found")
    return u


@router.get("")
def list_access(request: Request):
    cid = company_id(request)
    with get_db() as conn:
        customers = fetch_all(
            conn,
            """SELECT c.id AS customer_id, c.name, c.cnic, c.email AS customer_email, c.contact_number AS phone,
                      (SELECT COUNT(*) FROM bookings b WHERE b.customer_id=c.id AND b.status='active') AS active_bookings
               FROM customers c""",
        )
    with platform_db() as pconn:
        logins = {r["customer_id"]: r for r in fetch_all(
            pconn,
            """SELECT id AS user_id, customer_id, email AS login_email, is_active, last_login_at, must_change_password
               FROM users WHERE company_id=? AND role='customer'""",
            (cid,),
        )}
    for c in customers:
        login = logins.get(c["customer_id"]) or {}
        c.update({k: login.get(k) for k in ("user_id", "login_email", "is_active", "last_login_at",
                                            "must_change_password")})
    customers.sort(key=lambda c: (c["user_id"] is None, c["active_bookings"] == 0, c["name"] or ""))
    return customers


@router.post("")
def enable(body: EnableBody, request: Request, actor: dict = Depends(require_company_staff)):
    cid = company_id(request)
    with get_db() as conn:
        c = fetch_one(conn, "SELECT id, name, email, cnic FROM customers WHERE id=?", (body.customer_id,))
    if not c:
        raise HTTPException(404, "Customer not found")
    email = (body.email or c["email"] or "").strip()
    if not email:
        raise HTTPException(400, "Enter an email address for this customer's login")
    with platform_db() as pconn:
        try:
            user, temp = service.create_user(pconn, email=email, name=c["name"], role="customer", company_id=cid,
                                             customer_id=c["id"], customer_cnic=c["cnic"], created_by=actor["id"])
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    return {"user": user, "temporary_password": temp}


@router.post("/{user_id}/reset-password")
def reset(user_id: int, request: Request):
    cid = company_id(request)
    with platform_db() as conn:
        _customer_user(conn, user_id, cid)
        return {"temporary_password": service.reset_password(conn, user_id)}


@router.post("/{user_id}/status")
def set_status(user_id: int, body: StatusBody, request: Request):
    cid = company_id(request)
    with platform_db() as conn:
        _customer_user(conn, user_id, cid)
        return service.update_user(conn, user_id, is_active=body.is_active)
