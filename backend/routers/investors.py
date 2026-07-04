from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.database import get_db
from backend.services import investors as svc

router = APIRouter(prefix="/api/investors", tags=["investors"])


class InvestorCreate(BaseModel):
    name: str
    cnic: str | None = None
    mobile_number: str | None = None
    email: str | None = None
    description: str | None = None
    investor_type: str | None = None
    project_id: int | None = None
    investment_amount: int | None = None
    investment_date: str | None = None
    monthly_return_pct: float | None = None
    profit_share_pct: float | None = None


class MoneyBody(BaseModel):
    amount: int
    contribution_date: str | None = None
    distribution_date: str | None = None
    agreement_id: int | None = None
    notes: str | None = None


@router.get("")
def list_investors():
    with get_db() as conn:
        return svc.list_investors(conn)


@router.post("")
def create_investor(body: InvestorCreate):
    with get_db() as conn:
        return svc.create_investor(conn, body.model_dump())


@router.post("/{investor_id}/contribute")
def contribute(investor_id: int, body: MoneyBody):
    with get_db() as conn:
        try:
            return svc.add_contribution(conn, investor_id, {
                "amount": body.amount,
                "contribution_date": body.contribution_date,
                "agreement_id": body.agreement_id,
                "notes": body.notes,
            })
        except ValueError as e:
            raise HTTPException(400, str(e)) from e


@router.post("/{investor_id}/distribute")
def distribute(investor_id: int, body: MoneyBody):
    with get_db() as conn:
        try:
            return svc.add_distribution(conn, investor_id, {
                "amount": body.amount,
                "distribution_date": body.distribution_date,
                "agreement_id": body.agreement_id,
                "notes": body.notes,
            })
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
