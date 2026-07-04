import json
from backend.database import execute


def log(conn, entity_type: str, entity_id: int | None, action: str, details: dict | None = None):
    execute(
        conn,
        "INSERT INTO audit_log(entity_type, entity_id, action, details) VALUES(?,?,?,?)",
        (entity_type, entity_id, action, json.dumps(details or {})),
    )
