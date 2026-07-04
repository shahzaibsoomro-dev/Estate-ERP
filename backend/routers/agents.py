from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.database import get_db
from backend.services import agents as svc

router = APIRouter(prefix="/api/agents", tags=["agents"])


class AgentCreate(BaseModel):
    name: str
    description: str | None = None
    contact: str | None = None
    default_rate_pct: float = 2.0


class PayBody(BaseModel):
    amount: int
    payment_date: str
    notes: str | None = None


@router.get("")
def list_agents():
    with get_db() as conn:
        return svc.list_agents(conn)


@router.post("")
def create_agent(body: AgentCreate):
    with get_db() as conn:
        return svc.create_agent(conn, body.model_dump())


@router.post("/{agent_id}/pay")
def pay_agent(agent_id: int, body: PayBody):
    with get_db() as conn:
        return svc.pay_commission(conn, agent_id, body.amount, body.payment_date, body.notes)
