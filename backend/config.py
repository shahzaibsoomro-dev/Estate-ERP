import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("ERP_DB_PATH") or os.path.join(BASE_DIR, "db", "haven.db")
PLATFORM_DB_PATH = os.environ.get("ERP_PLATFORM_DB_PATH") or os.path.join(BASE_DIR, "db", "platform.db")
TENANTS_DIR = os.environ.get("ERP_TENANTS_DIR") or os.path.join(os.path.dirname(PLATFORM_DB_PATH), "tenants")
STATIC_DIR = os.path.join(BASE_DIR, "static")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "db", "schema.sql")
SCHEMA_VERSION = 2

DEFAULT_SETTINGS = {
    "po_cancel_fee_pct": "30",
    "late_fee_pct": "1",
    "default_agent_commission_pct": "2",
    "receipt_prefix": "RCP",
    "commission_on_booking": "true",
}
