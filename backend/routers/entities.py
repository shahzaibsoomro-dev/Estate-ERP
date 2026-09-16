from fastapi import APIRouter, HTTPException, Query
from backend.database import get_db
from backend.services import entities as svc

router = APIRouter(prefix="/api/entities", tags=["entities"])


@router.get("")
def list_entities(q: str | None = Query(None), type: str | None = Query(None)):
    with get_db() as conn:
        return svc.list_entities(conn, q=q, entity_type=type)


@router.get("/{entity_type}/{entity_id}")
def get_entity(entity_type: str, entity_id: int):
    with get_db() as conn:
        try:
            row = svc.get_entity(conn, entity_type.lower(), entity_id)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        if not row:
            raise HTTPException(404, "Entity not found")
        return row
