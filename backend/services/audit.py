import json
from backend.auth.context import current_ip, current_user_id
from backend.database import execute


def log(conn, entity_type: str, entity_id: int | None, action: str, details: dict | None = None,
        user_id: int | None = None):
    execute(
        conn,
        "INSERT INTO audit_log(entity_type, entity_id, action, details, user_id, ip) VALUES(?,?,?,?,?,?)",
        (entity_type, entity_id, action, json.dumps(details or {}),
         user_id if user_id is not None else current_user_id.get(), current_ip.get()),
    )
