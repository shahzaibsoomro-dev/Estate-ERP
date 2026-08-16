import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "db", "haven.db")
STATIC_DIR = os.path.join(BASE_DIR, "static")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "db", "schema.sql")
SCHEMA_VERSION = 2

DEFAULT_SETTINGS = {
    "cancellation_forfeit_pct": "30",
    "late_fee_pct": "1",
    "default_agent_commission_pct": "2",
    "receipt_prefix": "RCP",
    "commission_on_booking": "true",
}
