from fastapi import APIRouter, Query
from backend.database import get_db
from backend.services import dashboard as svc

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard")
def dashboard(project_id: int | None = Query(None)):
    with get_db() as conn:
        return svc.dashboard(conn, project_id)
