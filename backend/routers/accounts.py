from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from backend.database import get_db
from backend.services import accounts as svc
from backend.services.project_filter import parse_project_ids

router = APIRouter(prefix="/api", tags=["accounts"])


class LedgerCreate(BaseModel):
    entry_date: str
    narration: str
    amount: int | None = None
    direction: str | None = None
    category: str | None = None
    account_type: str | None = None
    debit: int | None = None
    credit: int | None = None
    notes: str | None = None
    payment_method: str | None = None
    project_id: int | None = None
    kind: str | None = None


class BalanceSet(BaseModel):
    cash: int = 0
    bank: int = 0
    as_of: str | None = None
    reason: str | None = None


def _http(exc: ValueError) -> HTTPException:
    msg = str(exc)
    if "not found" in msg.lower():
        return HTTPException(404, msg)
    return HTTPException(400, msg)


@router.get("/ledger")
def get_ledger(project_id: int | None = Query(None), project_ids: str | None = Query(None)):
    ids = parse_project_ids(project_ids, project_id)
    with get_db() as conn:
        return svc.list_cashbook(conn, ids)


@router.put("/ledger/balance")
def set_balance(body: BalanceSet):
    with get_db() as conn:
        try:
            return svc.set_current_balance(conn, body.model_dump())
        except ValueError as e:
            raise _http(e) from e


@router.post("/ledger")
def add_ledger(body: LedgerCreate):
    with get_db() as conn:
        try:
            return svc.create_ledger_entry(conn, body.model_dump())
        except ValueError as e:
            raise _http(e) from e


@router.delete("/ledger/{entry_id}")
def delete_ledger(entry_id: int):
    with get_db() as conn:
        try:
            svc.delete_ledger_entry(conn, entry_id)
            return {"ok": True}
        except ValueError as e:
            raise _http(e) from e
