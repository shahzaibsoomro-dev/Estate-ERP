from fastapi import APIRouter, Query
from backend.database import get_db
from backend.services import audit as audit_svc

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
def list_audit(
    limit: int = Query(200, ge=1, le=500),
    q: str | None = None,
    entity: str | None = Query(None, description="Filter by entity_type"),
    module: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    project_id: int | None = None,
):
    with get_db() as conn:
        return audit_svc.list_activity(
            conn,
            limit=limit,
            q=q,
            entity_type=entity,
            module=module,
            date_from=date_from,
            date_to=date_to,
            project_id=project_id,
        )
