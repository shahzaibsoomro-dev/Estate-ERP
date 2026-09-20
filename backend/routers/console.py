"""Platform console — super admins (developers) only."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from backend.auth import service
from backend.auth.deps import require_superadmin
from backend.database import fetch_all, fetch_one, platform_db
from backend.saas import service as saas

router = APIRouter(prefix="/api/console", tags=["console"], dependencies=[Depends(require_superadmin)])


def _err(e: Exception) -> HTTPException:
    return HTTPException(404 if isinstance(e, LookupError) else 400, str(e))


class CompanyCreate(BaseModel):
    name: str = Field(max_length=120)
    contact_name: str | None = Field(None, max_length=120)
    contact_email: str | None = Field(None, max_length=254)
    contact_phone: str | None = Field(None, max_length=40)
    city: str | None = Field(None, max_length=80)
    address: str | None = Field(None, max_length=300)
    notes: str | None = Field(None, max_length=1000)
    plan_id: int
    billing_cycle: Literal["monthly", "yearly"] = "monthly"
    amount: int | None = Field(None, ge=0)
    trial_days: int = Field(14, ge=0, le=90)
    grace_days: int = Field(7, ge=0, le=90)
    subscription_notes: str | None = Field(None, max_length=1000)
    admin_name: str = Field(max_length=120)
    admin_email: str = Field(max_length=254)
    seed_sample: bool = False


class CompanyUpdate(BaseModel):
    name: str | None = Field(None, max_length=120)
    contact_name: str | None = Field(None, max_length=120)
    contact_email: str | None = Field(None, max_length=254)
    contact_phone: str | None = Field(None, max_length=40)
    city: str | None = Field(None, max_length=80)
    address: str | None = Field(None, max_length=300)
    notes: str | None = Field(None, max_length=1000)
    status: Literal["active", "suspended"] | None = None


class SubscriptionUpdate(BaseModel):
    plan_id: int | None = None
    billing_cycle: Literal["monthly", "yearly"] | None = None
    amount: int | None = Field(None, ge=0)
    current_period_end: str | None = Field(None, max_length=10)
    grace_days: int | None = Field(None, ge=0, le=90)
    is_trial: bool | None = None
    notes: str | None = Field(None, max_length=1000)


class PaymentCreate(BaseModel):
    amount: int = Field(gt=0)
    paid_on: str = Field(max_length=10)
    method: str = Field(max_length=40)
    periods: int = Field(1, ge=1, le=36)
    reference: str | None = Field(None, max_length=120)
    notes: str | None = Field(None, max_length=500)


class VoidBody(BaseModel):
    reason: str = Field(max_length=300)


class PlanBody(BaseModel):
    name: str = Field(max_length=60)
    code: str | None = Field(None, max_length=40)
    price_monthly: int = Field(0, ge=0)
    price_yearly: int = Field(0, ge=0)
    max_employees: int | None = Field(None, ge=0)
    max_projects: int | None = Field(None, ge=0)
    description: str | None = Field(None, max_length=300)
    is_active: bool = True


class AdminCreate(BaseModel):
    name: str = Field(max_length=120)
    email: str = Field(max_length=254)


class UserStatus(BaseModel):
    is_active: bool


class SuperCreate(BaseModel):
    name: str = Field(max_length=120)
    email: str = Field(max_length=254)


# ---------------------------------------------------------------- overview / plans
@router.get("/overview")
def overview():
    with platform_db() as conn:
        return {**saas.overview(conn), "plans": saas.list_plans(conn), "payment_methods": saas.PAYMENT_METHODS}


@router.get("/plans")
def plans():
    with platform_db() as conn:
        return saas.list_plans(conn)


@router.post("/plans")
def create_plan(body: PlanBody):
    with platform_db() as conn:
        try:
            return saas.save_plan(conn, None, body.model_dump())
        except (ValueError, LookupError) as e:
            raise _err(e) from e


@router.put("/plans/{plan_id}")
def update_plan(plan_id: int, body: PlanBody):
    with platform_db() as conn:
        try:
            return saas.save_plan(conn, plan_id, body.model_dump())
        except (ValueError, LookupError) as e:
            raise _err(e) from e


# ---------------------------------------------------------------- companies
@router.get("/companies")
def companies():
    with platform_db() as conn:
        return saas.list_companies(conn)


@router.post("/companies")
def create_company(body: CompanyCreate, actor: dict = Depends(require_superadmin)):
    data = body.model_dump()
    admin_name, admin_email = data.pop("admin_name"), data.pop("admin_email")
    with platform_db() as conn:
        try:
            if fetch_one(conn, "SELECT id FROM users WHERE email=?", (admin_email.strip().lower(),)):
                raise ValueError("A user with the admin email already exists")
            company = saas.create_company(conn, **data)
            admin, temp = service.create_user(conn, email=admin_email, name=admin_name, role="admin",
                                              company_id=company["id"], created_by=actor["id"])
        except (ValueError, LookupError) as e:
            raise _err(e) from e
    company.pop("db_path", None)
    return {"company": company, "admin": admin, "temporary_password": temp}


@router.get("/companies/{company_id}")
def company(company_id: int):
    with platform_db() as conn:
        try:
            return saas.company_detail(conn, company_id)
        except LookupError as e:
            raise _err(e) from e


@router.patch("/companies/{company_id}")
def update_company(company_id: int, body: CompanyUpdate):
    with platform_db() as conn:
        try:
            c = saas.update_company(conn, company_id, body.model_dump(exclude_unset=True))
        except (ValueError, LookupError) as e:
            raise _err(e) from e
    c.pop("db_path", None)
    return c


@router.put("/companies/{company_id}/subscription")
def update_subscription(company_id: int, body: SubscriptionUpdate):
    with platform_db() as conn:
        try:
            return saas.update_subscription(conn, company_id, body.model_dump(exclude_unset=True))
        except (ValueError, LookupError) as e:
            raise _err(e) from e


@router.post("/companies/{company_id}/payments")
def record_payment(company_id: int, body: PaymentCreate, actor: dict = Depends(require_superadmin)):
    with platform_db() as conn:
        try:
            return saas.record_payment(conn, company_id, recorded_by=actor["id"], **body.model_dump())
        except (ValueError, LookupError) as e:
            raise _err(e) from e


@router.post("/payments/{payment_id}/void")
def void_payment(payment_id: int, body: VoidBody):
    with platform_db() as conn:
        try:
            return saas.void_payment(conn, payment_id, body.reason)
        except (ValueError, LookupError) as e:
            raise _err(e) from e


@router.get("/payments")
def payments():
    with platform_db() as conn:
        return saas.list_payments(conn)


# ---------------------------------------------------------------- company users (admin recovery)
def _company_user(conn, user_id: int) -> dict:
    u = service.get_user(conn, user_id)
    if not u or u["role"] == "superadmin":
        raise HTTPException(404, "User not found")
    return u


@router.post("/companies/{company_id}/admins")
def add_admin(company_id: int, body: AdminCreate, actor: dict = Depends(require_superadmin)):
    with platform_db() as conn:
        if not saas.get_company(conn, company_id):
            raise HTTPException(404, "Company not found")
        try:
            user, temp = service.create_user(conn, email=body.email, name=body.name, role="admin",
                                             company_id=company_id, created_by=actor["id"])
        except ValueError as e:
            raise _err(e) from e
    return {"user": user, "temporary_password": temp}


@router.post("/users/{user_id}/reset-password")
def reset_password(user_id: int):
    with platform_db() as conn:
        _company_user(conn, user_id)
        return {"temporary_password": service.reset_password(conn, user_id)}


@router.post("/users/{user_id}/unlock")
def unlock(user_id: int):
    with platform_db() as conn:
        u = _company_user(conn, user_id)
        service.clear_lockout(conn, user_id)
        saas.audit(conn, "user.unlock", company_id=u["company_id"], target_type="user", target_id=user_id)
    return {"ok": True}


@router.post("/users/{user_id}/status")
def set_status(user_id: int, body: UserStatus):
    with platform_db() as conn:
        _company_user(conn, user_id)
        return service.update_user(conn, user_id, is_active=body.is_active)


@router.post("/users/{user_id}/revoke-sessions")
def revoke_sessions(user_id: int):
    with platform_db() as conn:
        _company_user(conn, user_id)
        service.revoke_user_sessions(conn, user_id)
    return {"ok": True}


# ---------------------------------------------------------------- support mode
@router.post("/companies/{company_id}/support")
def enter_support(company_id: int, request: Request):
    with platform_db() as conn:
        c = saas.get_company(conn, company_id)
        if not c:
            raise HTTPException(404, "Company not found")
        service.set_session_company(conn, request.cookies.get("erp_session"), company_id, True)
        saas.audit(conn, "support.enter", company_id=company_id, target_type="company", target_id=company_id)
    return {"ok": True, "home": "/app"}


# ---------------------------------------------------------------- platform staff & audit
@router.get("/superadmins")
def superadmins():
    with platform_db() as conn:
        return service.list_users(conn, roles=("superadmin",))


@router.post("/superadmins")
def add_superadmin(body: SuperCreate, actor: dict = Depends(require_superadmin)):
    with platform_db() as conn:
        try:
            user, temp = service.create_user(conn, email=body.email, name=body.name, role="superadmin",
                                             created_by=actor["id"])
        except ValueError as e:
            raise _err(e) from e
    return {"user": user, "temporary_password": temp}


@router.post("/superadmins/{user_id}/status")
def superadmin_status(user_id: int, body: UserStatus, actor: dict = Depends(require_superadmin)):
    with platform_db() as conn:
        u = service.get_user(conn, user_id)
        if not u or u["role"] != "superadmin":
            raise HTTPException(404, "User not found")
        try:
            return service.update_user(conn, user_id, is_active=body.is_active, actor_id=actor["id"])
        except ValueError as e:
            raise _err(e) from e


@router.get("/activity")
def activity(company_id: int | None = None, limit: int = 200):
    with platform_db() as conn:
        sql = """SELECT a.*, u.name AS user_name, u.email AS user_email, u.role AS user_role, c.name AS company_name
                 FROM platform_audit a
                 LEFT JOIN users u ON u.id=a.user_id
                 LEFT JOIN companies c ON c.id=a.company_id"""
        params: tuple = ()
        if company_id:
            sql += " WHERE a.company_id=?"
            params = (company_id,)
        return fetch_all(conn, sql + " ORDER BY a.id DESC LIMIT ?", (*params, max(1, min(limit, 1000))))


@router.get("/users/{user_id}/locked")
def locked(user_id: int):
    with platform_db() as conn:
        return {"locked": service.is_locked(conn, user_id)}
