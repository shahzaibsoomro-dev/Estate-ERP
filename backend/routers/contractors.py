from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from backend.database import get_db
from backend.services import contractors as svc

router = APIRouter(prefix="/api/contractors", tags=["contractors"])


class ContractorWrite(BaseModel):
    name: str
    cnic: str | None = None
    contact: str | None = None
    ntn: str | None = None
    specialty: str | None = None
    description: str | None = None
    status: str | None = "active"


class AssignBody(BaseModel):
    project_id: int
    role: str | None = None
    contract_amount: int | None = 0
    start_date: str | None = None
    end_date: str | None = None
    status: str | None = "active"
    notes: str | None = None


class PayBody(BaseModel):
    amount: int
    payment_date: str | None = None
    project_id: int | None = None
    assignment_id: int | None = None
    payment_method: str | None = "Bank Transfer"
    reference_number: str | None = None
    notes: str | None = None


def _http(exc: ValueError) -> HTTPException:
    msg = str(exc)
    if "not found" in msg.lower():
        return HTTPException(404, msg)
    return HTTPException(400, msg)


@router.get("")
def list_contractors(project_ids: str | None = Query(None)):
    ids = None
    if project_ids:
        ids = [int(x) for x in project_ids.split(",") if x.strip().isdigit()]
    with get_db() as conn:
        return svc.list_contractors(conn, project_ids=ids)


@router.post("")
def create_contractor(body: ContractorWrite):
    with get_db() as conn:
        try:
            return svc.create_contractor(conn, body.model_dump())
        except ValueError as e:
            raise _http(e) from e


@router.get("/{contractor_id}")
def get_contractor(contractor_id: int):
    with get_db() as conn:
        row = svc.get_contractor(conn, contractor_id)
        if not row:
            raise HTTPException(404, "Contractor not found")
        return row


@router.put("/{contractor_id}")
def update_contractor(contractor_id: int, body: ContractorWrite):
    with get_db() as conn:
        try:
            row = svc.update_contractor(conn, contractor_id, body.model_dump())
        except ValueError as e:
            raise _http(e) from e
    if not row:
        raise HTTPException(404, "Contractor not found")
    return row


@router.delete("/{contractor_id}")
def delete_contractor(contractor_id: int):
    with get_db() as conn:
        try:
            svc.delete_contractor(conn, contractor_id)
            return {"ok": True}
        except ValueError as e:
            raise _http(e) from e


@router.post("/{contractor_id}/assign")
def assign(contractor_id: int, body: AssignBody):
    with get_db() as conn:
        try:
            return svc.assign_project(conn, contractor_id, body.model_dump())
        except ValueError as e:
            raise _http(e) from e


@router.post("/{contractor_id}/pay")
def pay(contractor_id: int, body: PayBody):
    with get_db() as conn:
        try:
            return svc.record_payment(conn, contractor_id, body.model_dump())
        except ValueError as e:
            raise _http(e) from e
