"""First-run super admin creation from environment variables."""
import os

from backend.auth import service
from backend.database import platform_db


def bootstrap_superadmin() -> None:
    email = os.environ.get("ERP_BOOTSTRAP_SUPERADMIN_EMAIL", "").strip()
    password = os.environ.get("ERP_BOOTSTRAP_SUPERADMIN_PASSWORD", "")
    with platform_db() as conn:
        if service.count_superadmins(conn) > 0:
            return
        if email and password:
            try:
                service.create_user(conn, email=email, name="Super Admin", role="superadmin",
                                    password=password, must_change_password=False)
                print(f"[auth] Super admin created for {email}")
            except ValueError as e:
                print(f"[auth] Could not create bootstrap super admin: {e}")
            return
    print(
        "\n[auth] First-time setup: open http://localhost:5050/setup on this computer to create\n"
        "       your super admin and company admin accounts.\n"
        "       (Or: python -m backend.manage create-superadmin)\n"
    )
