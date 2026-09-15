"""First-run setup: create the super admin and the admin for the existing company from the browser.

Only available while no super admin exists, and only from the computer running the server
(loopback, not via a reverse proxy) unless ERP_ALLOW_REMOTE_SETUP=1.
"""
import os

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.auth import service
from backend.auth.passwords import password_problems
from backend.database import fetch_all, fetch_one, get_db, platform_db
from backend.saas import service as saas

router = APIRouter(prefix="/api/setup", tags=["setup"])

LOOPBACK = {"127.0.0.1", "::1", "localhost"}


class Person(BaseModel):
    name: str = Field(max_length=120)
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)


class SetupBody(BaseModel):
    superadmin: Person
    admin: Person | None = None
    company_name: str | None = Field(None, max_length=120)


def _is_local(request: Request) -> bool:
    if os.environ.get("ERP_ALLOW_REMOTE_SETUP") == "1":
        return True
    if request.headers.get("x-forwarded-for") or request.headers.get("forwarded"):
        return False  # behind a proxy the peer address says nothing about the real client
    host = request.client.host if request.client else ""
    return host in LOOPBACK


def _state(conn) -> dict:
    needed = service.count_superadmins(conn) == 0
    company = fetch_one(conn, "SELECT id, name, db_path FROM companies ORDER BY id LIMIT 1")
    admins = []
    counts = {}
    if company:
        admins = fetch_all(conn, "SELECT name, email FROM users WHERE company_id=? AND role='admin' AND is_active=1",
                           (company["id"],))
        with get_db(saas.resolve_db_path(company["db_path"])) as tconn:
            q = lambda sql: tconn.execute(sql).fetchone()[0]  # noqa: E731
            counts = {"projects": q("SELECT COUNT(*) FROM projects"), "units": q("SELECT COUNT(*) FROM units"),
                      "customers": q("SELECT COUNT(*) FROM customers"),
                      "bookings": q("SELECT COUNT(*) FROM bookings WHERE status='active'")}
    return {"needed": needed, "company": ({"name": company["name"], **counts} if company else None),
            "existing_admins": admins}


@router.get("/status")
def status(request: Request):
    with platform_db() as conn:
        st = _state(conn)
    st["allowed_here"] = _is_local(request)
    if not st["needed"]:
        return {"needed": False}
    return st


@router.post("")
def run_setup(body: SetupBody, request: Request):
    if not _is_local(request):
        raise HTTPException(403, "For security, first-time setup must be done on the computer running the server "
                                 "(open http://localhost:5050/setup there).")
    sa, ad = body.superadmin, body.admin
    for label, p in (("Super admin", sa), ("Admin", ad)):
        if p is None:
            continue
        problems = password_problems(p.password, p.email)
        if problems:
            raise HTTPException(400, f"{label} password needs " + ", ".join(problems))
    if ad and ad.email.strip().lower() == sa.email.strip().lower():
        raise HTTPException(400, "Use a different email for the admin account than for the super admin")
    with platform_db() as conn:
        if service.count_superadmins(conn) > 0:
            raise HTTPException(409, "Setup has already been completed. Please sign in.")
        company = fetch_one(conn, "SELECT * FROM companies ORDER BY id LIMIT 1")
        if ad and not company:
            raise HTTPException(400, "No company data found to attach the admin to")
        try:
            su, _ = service.create_user(conn, email=sa.email, name=sa.name, role="superadmin",
                                        password=sa.password, must_change_password=False)
            created = {"superadmin": service.public_user(su)}
            if ad:
                au, _ = service.create_user(conn, email=ad.email, name=ad.name, role="admin",
                                            company_id=company["id"], password=ad.password,
                                            must_change_password=False, created_by=su["id"])
                created["admin"] = service.public_user(au)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e  # rolls back both accounts
        new_name = (body.company_name or "").strip()
        if company and new_name and new_name != company["name"]:
            saas.update_company(conn, company["id"], {"name": new_name})
            with get_db(saas.resolve_db_path(company["db_path"])) as tconn:
                tconn.execute("INSERT OR REPLACE INTO company_settings(key, value) VALUES('company_name', ?)",
                              (new_name,))
        saas.audit(conn, "setup.complete", company_id=company["id"] if company else None,
                   details={"superadmin": sa.email, "admin": ad.email if ad else None}, user_id=su["id"])
    return {"ok": True, **created}
