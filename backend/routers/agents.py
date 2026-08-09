from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from backend.database import get_db
from backend.services import agents as svc

router = APIRouter(prefix="/api/agents", tags=["agents"])


class AgentWrite(BaseModel):
    name: str
    description: str | None = None
    contact: str | None = None
    category: str | None = None
    default_rate_pct: float = 2.0
    status: str | None = "active"


class PayBody(BaseModel):
    amount: int
    payment_date: str | None = None
    notes: str | None = None
    commission_id: int | None = None


def _http(exc: ValueError) -> HTTPException:
    msg = str(exc)
    if "not found" in msg.lower():
        return HTTPException(404, msg)
    return HTTPException(400, msg)


@router.get("")
def list_agents(active_only: bool = Query(False)):
    with get_db() as conn:
        return svc.list_agents(conn, active_only=active_only)


@router.post("")
def create_agent(body: AgentWrite):
    with get_db() as conn:
        try:
            return svc.create_agent(conn, body.model_dump())
        except ValueError as e:
            raise _http(e) from e


@router.get("/{agent_id}")
def get_agent(agent_id: int):
    with get_db() as conn:
        ag = svc.get_agent(conn, agent_id)
        if not ag:
            raise HTTPException(404, "Agent not found")
        return ag


@router.put("/{agent_id}")
def update_agent(agent_id: int, body: AgentWrite):
    with get_db() as conn:
        try:
            ag = svc.update_agent(conn, agent_id, body.model_dump())
        except ValueError as e:
            raise _http(e) from e
    if not ag:
        raise HTTPException(404, "Agent not found")
    return ag


@router.delete("/{agent_id}")
def delete_agent(agent_id: int):
    with get_db() as conn:
        try:
            svc.delete_agent(conn, agent_id)
            return {"ok": True}
        except ValueError as e:
            raise _http(e) from e


@router.post("/{agent_id}/pay")
def pay_agent(agent_id: int, body: PayBody):
    with get_db() as conn:
        try:
            return svc.pay_commission(
                conn, agent_id, body.amount, body.payment_date, body.notes, body.commission_id,
            )
        except ValueError as e:
            raise _http(e) from e
