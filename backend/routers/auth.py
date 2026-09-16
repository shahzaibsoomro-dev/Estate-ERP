from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from backend.auth import permissions as P
from backend.auth import service
from backend.auth.deps import current_session, current_user
from backend.auth.middleware import clear_session_cookie, client_ip, home_for, set_session_cookie
from backend.database import platform_db
from backend.saas.service import audit, get_subscription

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    identifier: str = Field(max_length=254)
    password: str = Field(max_length=256)


class ChangePasswordBody(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


def me_payload(request: Request, sess: dict | None = None) -> dict:
    sess = sess or request.state.session
    user = sess["user"]
    out = service.public_user(user)
    out["home"] = home_for(user, sess["support_mode"])
    out["csrf_token"] = sess["csrf_token"]
    out["support_mode"] = sess["support_mode"]
    company = sess.get("company")
    out["company"] = {"id": company["id"], "name": company["name"], "slug": company["slug"]} if company else None
    state = getattr(request.state, "company_state", None)
    if company and user["role"] != "customer":
        out["subscription"] = state
        with platform_db() as conn:
            sub = get_subscription(conn, company["id"])
        if sub and out["subscription"] is not None:
            out["subscription"] = {**state, "plan_name": sub["plan_name"]}
    if user["role"] == "employee":
        out["permissions"] = sess["permissions"]
        out["project_ids"] = sess["project_ids"]
    elif user["role"] in ("admin", "superadmin") and company:
        out["permissions"] = {m: {a: a in acts for a in P.ACTIONS} for m, acts in P.MODULE_ACTIONS.items()}
        out["project_ids"] = None
    return out


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response):
    error = None
    with platform_db() as conn:  # commits even on failure so throttling counts the attempt
        try:
            user = service.authenticate(conn, body.identifier, body.password, client_ip(request))
            service.revoke_session(conn, request.cookies.get("erp_session"))  # session fixation
            token, _ = service.create_session(conn, user, client_ip(request), request.headers.get("user-agent"))
            sess = service.resolve_session(conn, token)
        except service.AuthError as e:
            error = str(e)
    if error:
        code = 429 if error.startswith("Too many") else 403 if "suspended" in error else 401
        raise HTTPException(code, error)
    set_session_cookie(request, response, token)
    request.state.company_state = None
    if sess["company"]:
        from backend.saas.service import company_state
        with platform_db() as conn:
            request.state.company_state = company_state(conn, sess["company"]["id"])
    return me_payload(request, sess)


@router.post("/logout")
def logout(request: Request, response: Response):
    with platform_db() as conn:
        user = getattr(request.state, "user", None)
        service.revoke_session(conn, request.cookies.get("erp_session"))
        if user:
            audit(conn, "auth.logout", company_id=user.get("company_id"), target_type="user", target_id=user["id"])
    clear_session_cookie(response)
    return {"ok": True}


@router.get("/session")
def session_probe(request: Request):
    """Public: whether someone is signed in (never 401s)."""
    if not getattr(request.state, "user", None):
        return {"authenticated": False}
    return {"authenticated": True, **me_payload(request)}


@router.get("/me")
def me(request: Request):
    current_user(request)
    return me_payload(request)


@router.post("/exit-support")
def exit_support(request: Request):
    sess = current_session(request)
    if sess["user"]["role"] != "superadmin" or not sess["support_mode"]:
        raise HTTPException(400, "Not in support mode")
    with platform_db() as conn:
        service.set_session_company(conn, request.cookies.get("erp_session"), None, False)
        audit(conn, "support.exit", company_id=sess["company"]["id"], target_type="company",
              target_id=sess["company"]["id"])
    return {"ok": True, "home": "/console"}


@router.post("/change-password")
def change_password(body: ChangePasswordBody, request: Request):
    sess = current_session(request)
    user = sess["user"]
    with platform_db() as conn:
        try:
            service.change_password(conn, user["id"], body.current_password, body.new_password, sess["token_hash"])
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        fresh = service.resolve_session(conn, request.cookies.get("erp_session"))
    return me_payload(request, fresh)
