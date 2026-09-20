"""Throwaway dev server on an isolated copy of the sample data, for UI smoke-testing."""
import os
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
tmp = Path(tempfile.mkdtemp(prefix="erp-ui-"))
src = ROOT / "db" / "haven.pre-sim.db"
if not src.exists():
    src = ROOT / "db" / "haven.db"
shutil.copy(src, tmp / "haven.db")
os.environ["ERP_DB_PATH"] = str(tmp / "haven.db")
os.environ["ERP_PLATFORM_DB_PATH"] = str(tmp / "platform.db")
os.environ["ERP_TENANTS_DIR"] = str(tmp / "tenants")
os.environ["ERP_LOGIN_MAX_FAILS_PER_IP"] = "1000"

from backend.auth import service  # noqa: E402
from backend.database import fetch_one, platform_db  # noqa: E402
from backend.main import app  # noqa: E402
from backend.saas.service import bootstrap_platform  # noqa: E402

bootstrap_platform()
EMAIL, PASSWORD = "uidev@test.local", "Str0ng-Test-Pass"
with platform_db() as conn:
    company = fetch_one(conn, "SELECT * FROM companies ORDER BY id LIMIT 1")
    if not fetch_one(conn, "SELECT id FROM users WHERE email=?", (EMAIL,)):
        service.create_user(conn, email=EMAIL, name="UI Dev", role="admin", company_id=company["id"],
                            password=PASSWORD, must_change_password=False)
print(f"[ui-dev] {EMAIL} / {PASSWORD} · data in {tmp}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=5058, log_level="warning")
