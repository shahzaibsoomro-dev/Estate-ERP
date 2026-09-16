from fastapi import APIRouter, Query
from backend.database import get_db
from backend.services import dashboard as svc
from backend.services.project_filter import parse_project_ids

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard")
def dashboard(
    project_id: int | None = Query(None),
    project_ids: str | None = Query(None),
):
    ids = parse_project_ids(project_ids, project_id)
    with get_db() as conn:
        return svc.dashboard(conn, ids)
