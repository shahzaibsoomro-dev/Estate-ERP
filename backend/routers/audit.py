import json
from fastapi import APIRouter, Query
from backend.database import fetch_all, get_db

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
def list_audit(limit: int = Query(200, ge=1, le=500)):
    with get_db() as conn:
        rows = fetch_all(
            conn,
            """SELECT id, entity_type, entity_id, action, details, created_at
               FROM audit_log ORDER BY id DESC LIMIT ?""",
            (limit,),
        )
    for r in rows:
        raw = r.get("details")
        if isinstance(raw, str) and raw:
            try:
                r["details"] = json.loads(raw)
            except json.JSONDecodeError:
                pass
    return rows
