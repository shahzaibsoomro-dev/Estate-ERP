from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from backend.database import get_db
from backend.services import inventory as svc

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


class ItemWrite(BaseModel):
    name: str
    sku: str | None = None
    unit: str | None = "pcs"
    category: str | None = None
    project_id: int | None = None
    min_stock: float | None = 0
    notes: str | None = None
    status: str | None = "active"
    opening_stock: float | None = 0
    unit_cost: int | None = 0


class MovementBody(BaseModel):
    direction: str
    quantity: float
    project_id: int | None = None
    unit_cost: int | None = 0
    movement_date: str | None = None
    notes: str | None = None
    reference_type: str | None = None
    reference_id: int | None = None


def _http(exc: ValueError) -> HTTPException:
    msg = str(exc)
    if "not found" in msg.lower():
        return HTTPException(404, msg)
    return HTTPException(400, msg)


@router.get("")
def list_items(project_id: int | None = Query(None), project_ids: str | None = Query(None)):
    ids = None
    if project_ids:
        ids = [int(x) for x in project_ids.split(",") if x.strip().isdigit()]
    with get_db() as conn:
        return svc.list_items(conn, project_id=project_id, project_ids=ids)


@router.post("")
def create_item(body: ItemWrite):
    with get_db() as conn:
        try:
            return svc.create_item(conn, body.model_dump())
        except ValueError as e:
            raise _http(e) from e


@router.get("/{item_id}")
def get_item(item_id: int):
    with get_db() as conn:
        row = svc.get_item(conn, item_id)
        if not row:
            raise HTTPException(404, "Inventory item not found")
        return row


@router.put("/{item_id}")
def update_item(item_id: int, body: ItemWrite):
    with get_db() as conn:
        try:
            row = svc.update_item(conn, item_id, body.model_dump())
        except ValueError as e:
            raise _http(e) from e
    if not row:
        raise HTTPException(404, "Inventory item not found")
    return row


@router.post("/{item_id}/move")
def move_stock(item_id: int, body: MovementBody):
    with get_db() as conn:
        try:
            return svc.add_movement(conn, item_id, body.model_dump())
        except ValueError as e:
            raise _http(e) from e
