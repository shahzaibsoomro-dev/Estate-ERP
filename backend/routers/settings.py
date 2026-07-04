from fastapi import APIRouter
from backend.database import get_db
from backend.services import settings as settings_svc

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_settings():
    with get_db() as conn:
        return settings_svc.get_all(conn)


@router.put("/{key}")
def update_setting(key: str, body: dict):
    with get_db() as conn:
        return settings_svc.set_value(conn, key, str(body.get("value", "")))
