"""Company admin area: employees & their permissions, subscription status, sign-in activity."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from backend.auth import permissions as P
from backend.auth import service
from backend.auth.deps import company_id, require_company_admin
from backend.database import fetch_all, get_db, platform_db
from backend.saas import service as saas

router = APIRouter(prefix="/api/company", tags=["company-admin"], dependencies=[Depends(require_company_admin)])


class EmployeeBody(BaseModel):
    name: str = Field(max_length=120)
    email: str | None = Field(None, max_length=254)
    job_title: str | None = Field(None, max_length=80)
    permissions: dict = Field(default_factory=dict)
    all_projects: bool = True
    project_ids: list[int] = Field(default_factory=list, max_length=500)


class StatusBody(BaseModel):
    is_active: bool


def _employee(conn, user_id: int, cid: int) -> dict:
    u = service.get_user(conn, user_id)
    if not u or u["company_id"] != cid or u["role"] != "employee":
        raise HTTPException(404, "Employee not found")
    return u


def _valid_projects(ids: list[int]) -> list[int]:
    if not ids:
        return []
    with get_db() as tconn:
        found = {r["id"] for r in fetch_all(
            tconn, f"SELECT id FROM projects WHERE id IN ({','.join('?' * len(ids))})", tuple(ids))}
    missing = set(ids) - found
    if missing:
        raise HTTPException(400, "Unknown project selected")
    return sorted(found)


def _with_access(conn, u: dict) -> dict:
    u = dict(u)
    u["permissions"] = service.get_permissions(conn, u["id"])
    u["project_ids"] = None if u["all_projects"] else service.get_project_ids(conn, u["id"])
    u["locked"] = service.is_locked(conn, u["id"])
    return u


@router.get("/access-catalogue")
def catalogue():
    return P.catalogue()


@router.get("/employees")
def employees(request: Request):
    cid = company_id(request)
    with platform_db() as conn:
        rows = service.list_users(conn, company_id=cid, roles=("admin", "employee"))
        return [_with_access(conn, u) if u["role"] == "employee" else {**u, "locked": service.is_locked(conn, u["id"])}
                for u in rows]


@router.post("/employees")
def create_employee(body: EmployeeBody, request: Request, actor: dict = Depends(require_company_admin)):
    cid = company_id(request)
    if not body.email:
        raise HTTPException(400, "Email is required")
    if not body.all_projects and not body.project_ids:
        raise HTTPException(400, "Select at least one project, or allow all projects")
    projects = _valid_projects(body.project_ids) if not body.all_projects else []
    with platform_db() as conn:
        try:
            count = fetch_all(conn, "SELECT COUNT(*) n FROM users WHERE company_id=? AND role='employee' AND is_active=1",
                              (cid,))[0]["n"]
            saas.check_limit(conn, cid, "employees", count)
            user, temp = service.create_user(conn, email=body.email, name=body.name, role="employee",
                                             company_id=cid, job_title=body.job_title, created_by=actor["id"])
            service.set_employee_access(conn, user["id"], permissions=body.permissions,
                                        all_projects=body.all_projects, project_ids=projects)
            return {"user": _with_access(conn, service.get_user(conn, user["id"])), "temporary_password": temp}
        except ValueError as e:
            raise HTTPException(400, str(e)) from e


@router.put("/employees/{user_id}")
def update_employee(user_id: int, body: EmployeeBody, request: Request):
    cid = company_id(request)
    if not body.all_projects and not body.project_ids:
        raise HTTPException(400, "Select at least one project, or allow all projects")
    projects = _valid_projects(body.project_ids) if not body.all_projects else []
    with platform_db() as conn:
        _employee(conn, user_id, cid)
        service.update_user(conn, user_id, name=body.name, job_title=body.job_title or "")
        service.set_employee_access(conn, user_id, permissions=body.permissions,
                                    all_projects=body.all_projects, project_ids=projects)
        saas.audit(conn, "employee.access", company_id=cid, target_type="user", target_id=user_id,
                   details={"modules": sorted(P.normalize_permissions(body.permissions)),
                            "all_projects": body.all_projects, "projects": projects})
        return _with_access(conn, service.get_user(conn, user_id))


@router.post("/employees/{user_id}/reset-password")
def reset_employee(user_id: int, request: Request):
    cid = company_id(request)
    with platform_db() as conn:
        _employee(conn, user_id, cid)
        return {"temporary_password": service.reset_password(conn, user_id)}


@router.post("/employees/{user_id}/unlock")
def unlock_employee(user_id: int, request: Request):
    cid = company_id(request)
    with platform_db() as conn:
        _employee(conn, user_id, cid)
        service.clear_lockout(conn, user_id)
        saas.audit(conn, "user.unlock", company_id=cid, target_type="user", target_id=user_id)
    return {"ok": True}


@router.post("/employees/{user_id}/status")
def employee_status(user_id: int, body: StatusBody, request: Request):
    cid = company_id(request)
    with platform_db() as conn:
        _employee(conn, user_id, cid)
        if body.is_active:
            count = fetch_all(conn, "SELECT COUNT(*) n FROM users WHERE company_id=? AND role='employee' AND is_active=1",
                              (cid,))[0]["n"]
            try:
                saas.check_limit(conn, cid, "employees", count)
            except ValueError as e:
                raise HTTPException(400, str(e)) from e
        return service.update_user(conn, user_id, is_active=body.is_active)


@router.get("/subscription")
def subscription(request: Request):
    cid = company_id(request)
    with platform_db() as conn:
        c = saas.get_company(conn, cid)
        sub = saas.get_subscription(conn, cid)
        employees = fetch_all(conn, "SELECT COUNT(*) n FROM users WHERE company_id=? AND role='employee' AND is_active=1",
                              (cid,))[0]["n"]
        payments = [
            {k: p[k] for k in ("receipt_no", "amount", "paid_on", "method", "reference", "period_start",
                               "period_end", "voided_at")}
            for p in saas.list_payments(conn, cid)
        ]
    with get_db() as tconn:
        projects = fetch_all(tconn, "SELECT COUNT(*) n FROM projects")[0]["n"]
    return {
        "company": {"name": c["name"], "contact_email": c["contact_email"], "contact_phone": c["contact_phone"]},
        "subscription": {k: sub[k] for k in ("plan_name", "billing_cycle", "amount", "is_trial", "started_on",
                                             "current_period_end", "grace_days", "max_employees", "max_projects")}
        if sub else None,
        "state": saas.subscription_state(c, sub),
        "usage": {"employees": employees, "projects": projects},
        "payments": payments,
    }


@router.get("/activity")
def activity(request: Request, limit: int = 200):
    cid = company_id(request)
    with platform_db() as conn:
        return fetch_all(
            conn,
            """SELECT a.id, a.action, a.created_at, a.ip, a.details, u.email, u.name, u.role
               FROM platform_audit a LEFT JOIN users u ON u.id=a.user_id
               WHERE a.company_id=? AND (u.role IS NULL OR u.role != 'superadmin' OR a.action LIKE 'support.%')
               ORDER BY a.id DESC LIMIT ?""",
            (cid, max(1, min(limit, 500))),
        )
