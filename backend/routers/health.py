from fastapi import APIRouter
from backend.database import fetch_one, get_db

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health():
    with get_db() as conn:
        cnt = fetch_one(conn, "SELECT COUNT(*) AS n FROM units")
        return {"status": "ok", "units_in_db": cnt["n"] if cnt else 0}
