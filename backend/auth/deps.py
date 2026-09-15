"""FastAPI dependencies — a second line of defence behind the middleware."""
from fastapi import HTTPException, Request


def current_user(request: Request) -> dict:
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(401, "Not authenticated")
    return user


def current_session(request: Request) -> dict:
    current_user(request)
    return request.state.session


def require_superadmin(request: Request) -> dict:
    user = current_user(request)
    if user["role"] != "superadmin":
        raise HTTPException(403, "You do not have access to this area")
    return user


def require_customer(request: Request) -> dict:
    user = current_user(request)
    if user["role"] != "customer" or not user.get("customer_id"):
        raise HTTPException(403, "You do not have access to this area")
    return user


def _in_company(request: Request) -> dict:
    sess = current_session(request)
    role = sess["user"]["role"]
    if not sess.get("company") or not (role in ("admin", "employee") or (role == "superadmin" and sess["support_mode"])):
        raise HTTPException(403, "You do not have access to this area")
    return sess


def require_company_staff(request: Request) -> dict:
    """Admin, employee (permissions checked by middleware) or superadmin in support mode."""
    return _in_company(request)["user"]


def require_company_admin(request: Request) -> dict:
    sess = _in_company(request)
    if sess["user"]["role"] == "employee":
        raise HTTPException(403, "Only company admins can do this")
    return sess["user"]


def company_id(request: Request) -> int:
    return _in_company(request)["company"]["id"]


# Backwards-compatible alias used by existing routers.
require_staff = require_company_staff
