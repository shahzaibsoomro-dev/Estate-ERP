from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.database import get_db
from backend.services import partners as svc

router = APIRouter(prefix="/api/partners", tags=["partners"])


class PartnerWrite(BaseModel):
    name: str
    cnic: str | None = None
    mobile_number: str | None = None
    contact: str | None = None
    email: str | None = None
    description: str | None = None
    status: str | None = "active"
    partner_type: str | None = None
    investor_type: str | None = None  # alias accepted from shared UI payloads
    return_type: str | None = None
    project_id: int | None = None
    agreed_amount: int | None = None
    investment_date: str | None = None
    monthly_return_pct: float | None = None
    profit_share_pct: float | None = None
    returns_start_date: str | None = None
    catch_up_policy: str | None = "lump_sum"
    catch_up_months: int | None = None
    profit_share_basis: str | None = None


class MoneyBody(BaseModel):
    amount: int
    contribution_date: str | None = None
    distribution_date: str | None = None
    agreement_id: int | None = None
    notes: str | None = None


def _http(exc: ValueError) -> HTTPException:
    msg = str(exc)
    if "not found" in msg.lower():
        return HTTPException(404, msg)
    return HTTPException(400, msg)


@router.get("")
def list_partners():
    with get_db() as conn:
        return svc.list_partners(conn)


@router.post("")
def create_partner(body: PartnerWrite):
    with get_db() as conn:
        try:
            return svc.create_partner(conn, body.model_dump())
        except ValueError as e:
            raise _http(e) from e


@router.get("/{partner_id}")
def get_partner(partner_id: int):
    with get_db() as conn:
        partner = svc.get_partner(conn, partner_id)
        if not partner:
            raise HTTPException(404, "Partner not found")
        return partner


@router.put("/{partner_id}")
def update_partner(partner_id: int, body: PartnerWrite):
    with get_db() as conn:
        try:
            partner = svc.update_partner(conn, partner_id, body.model_dump())
        except ValueError as e:
            raise _http(e) from e
    if not partner:
        raise HTTPException(404, "Partner not found")
    return partner


@router.delete("/{partner_id}")
def delete_partner(partner_id: int):
    with get_db() as conn:
        try:
            svc.delete_partner(conn, partner_id)
            return {"ok": True}
        except ValueError as e:
            raise _http(e) from e


@router.post("/{partner_id}/contribute")
def contribute(partner_id: int, body: MoneyBody):
    with get_db() as conn:
        try:
            return svc.add_contribution(conn, partner_id, body.model_dump())
        except ValueError as e:
            raise _http(e) from e


@router.post("/{partner_id}/distribute")
def distribute(partner_id: int, body: MoneyBody):
    with get_db() as conn:
        try:
            return svc.add_distribution(conn, partner_id, body.model_dump())
        except ValueError as e:
            raise _http(e) from e
