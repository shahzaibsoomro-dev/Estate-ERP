from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.database import get_db
from backend.services import investors as svc

router = APIRouter(prefix="/api/investors", tags=["investors"])


class InvestorWrite(BaseModel):
    name: str
    cnic: str | None = None
    mobile_number: str | None = None
    contact: str | None = None
    email: str | None = None
    description: str | None = None
    status: str | None = "active"
    investor_type: str | None = None
    project_id: int | None = None
    agreed_amount: int | None = None
    investment_date: str | None = None
    monthly_return_pct: float | None = None
    profit_share_pct: float | None = None


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
def list_investors():
    with get_db() as conn:
        return svc.list_investors(conn)


@router.post("")
def create_investor(body: InvestorWrite):
    with get_db() as conn:
        try:
            return svc.create_investor(conn, body.model_dump())
        except ValueError as e:
            raise _http(e) from e


@router.get("/{investor_id}")
def get_investor(investor_id: int):
    with get_db() as conn:
        inv = svc.get_investor(conn, investor_id)
        if not inv:
            raise HTTPException(404, "Investor not found")
        return inv


@router.put("/{investor_id}")
def update_investor(investor_id: int, body: InvestorWrite):
    with get_db() as conn:
        try:
            inv = svc.update_investor(conn, investor_id, body.model_dump())
        except ValueError as e:
            raise _http(e) from e
    if not inv:
        raise HTTPException(404, "Investor not found")
    return inv


@router.delete("/{investor_id}")
def delete_investor(investor_id: int):
    with get_db() as conn:
        try:
            svc.delete_investor(conn, investor_id)
            return {"ok": True}
        except ValueError as e:
            raise _http(e) from e


@router.post("/{investor_id}/contribute")
def contribute(investor_id: int, body: MoneyBody):
    with get_db() as conn:
        try:
            return svc.add_contribution(conn, investor_id, body.model_dump())
        except ValueError as e:
            raise _http(e) from e


@router.post("/{investor_id}/distribute")
def distribute(investor_id: int, body: MoneyBody):
    with get_db() as conn:
        try:
            return svc.add_distribution(conn, investor_id, body.model_dump())
        except ValueError as e:
            raise _http(e) from e
