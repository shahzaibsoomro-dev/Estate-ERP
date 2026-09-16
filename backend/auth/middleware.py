"""Deny-by-default access control, company routing, subscription state, CSRF and security headers.

Areas (by path):
  public      homepage, login, static assets, /api/public/*, /api/auth/login|session, /api/health
  any         any signed-in user (/api/auth/*, /documents/* — handlers check ownership)
  customer    owner portal (/portal, /api/me/*)
  console     platform console for super admins (/console, /api/console/*, API docs)
  company     everything else: the ERP (/app + business APIs) for admins, employees,
              and super admins who opened a company in support mode

Company requests are routed to that company's own database. Employees are further
limited by their permission matrix (module × view/add/edit/delete) and project list.
"""
import hmac
import json
from urllib.parse import parse_qsl, quote, urlsplit

from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from backend.auth import permissions as P
from backend.auth import service
from backend.auth import settings as cfg
from backend.auth.context import current_ip, current_user_id
from backend.auth.scope import Scope, ScopeDenied
from backend.database import current_db_path, platform_db
from backend.saas.service import company_state, resolve_db_path

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

PUBLIC_EXACT = {"/", "/login", "/setup", "/api/setup", "/api/setup/status", "/favicon.ico", "/robots.txt", "/api/health", "/api/auth/login", "/api/auth/session"}
PUBLIC_PREFIX = ("/static/", "/api/public/", "/c/")
ANY_EXACT = {"/api/auth/me", "/api/auth/logout", "/api/auth/change-password", "/account/password",
             "/api/auth/exit-support"}
ANY_PREFIX = ("/documents/",)
CUSTOMER_EXACT = {"/portal"}
CUSTOMER_PREFIX = ("/api/me/",)
CONSOLE_EXACT = {"/console", "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}
CONSOLE_PREFIX = ("/api/console/",)
# Company endpoints only admins (not employees) may use, regardless of permissions.
ADMIN_ONLY_PREFIX = ("/api/company/", "/api/settings/")
# Still reachable while a password change is pending.
PENDING_PW_ALLOWED = {"/api/auth/me", "/api/auth/logout", "/api/auth/change-password", "/account/password",
                      "/api/auth/session"}
# Reachable when the subscription has expired (read-only mode) even though they are writes.
READONLY_ALLOWED_WRITES = {"/api/auth/logout", "/api/auth/change-password", "/api/auth/exit-support"}


def home_for(user: dict, support_mode: bool = False) -> str:
    if user["role"] == "superadmin":
        return "/app" if support_mode else "/console"
    return "/portal" if user["role"] == "customer" else "/app"


def area_of(path: str) -> str:
    if path in PUBLIC_EXACT or path.startswith(PUBLIC_PREFIX):
        return "public"
    if path in ANY_EXACT or path.startswith(ANY_PREFIX):
        return "any"
    if path in CUSTOMER_EXACT or path.startswith(CUSTOMER_PREFIX):
        return "customer"
    if path in CONSOLE_EXACT or path.startswith(CONSOLE_PREFIX):
        return "console"
    return "company"


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _is_api(path: str) -> bool:
    return path.startswith("/api/") or path == "/openapi.json"


def _origin_ok(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        ref = request.headers.get("referer")
        if not ref:
            return True  # non-browser clients; the CSRF token still applies
        parts = urlsplit(ref)
        origin = f"{parts.scheme}://{parts.netloc}"
    host = request.headers.get("host", "")
    return origin in {f"http://{host}", f"https://{host}", *cfg.CORS_ORIGINS}


def _deny(request: Request, status: int, detail: str, redirect_to: str | None = None) -> Response:
    if _is_api(request.url.path) or request.method not in SAFE_METHODS or not redirect_to:
        return JSONResponse({"detail": detail}, status_code=status)
    return RedirectResponse(redirect_to, status_code=303)


def _is_https(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"


CSP = (
    "default-src 'self'; script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com data:; img-src 'self' data:; "
    "connect-src 'self'; frame-ancestors 'self'; base-uri 'self'; form-action 'self'; object-src 'none'"
)


def _secure_headers(request: Request, response: Response) -> Response:
    h = response.headers
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("X-Frame-Options", "SAMEORIGIN")
    h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    path = request.url.path
    if not (path.startswith("/docs") or path == "/redoc"):
        h.setdefault("Content-Security-Policy", CSP)
    if _is_https(request):
        h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if not path.startswith("/static/"):
        h.setdefault("Cache-Control", "no-store")
    return response


def _employee_allowed(sess: dict, method: str, path: str) -> tuple[bool, str]:
    """Check the permission matrix. Returns (allowed, action)."""
    rule = P.match_route(method, path)
    if rule is None:
        return False, "admin"
    modules, action = rule
    perms = sess["permissions"] or {}
    scoped = sess["project_ids"] is not None
    if modules == ("*",):
        return bool(perms), action
    for mod in modules:
        if scoped and mod in P.NEEDS_ALL_PROJECTS:
            continue
        if perms.get(mod, {}).get(action):
            return True, action
    return False, action


def _action_for(method: str, path: str) -> str:
    rule = P.match_route(method, path)
    if rule:
        return rule[1]
    return "view" if method in SAFE_METHODS else "edit"


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        area = area_of(path)
        method = request.method
        request.state.user = None
        request.state.session = None

        if method not in SAFE_METHODS and not _origin_ok(request):
            return _secure_headers(request, JSONResponse({"detail": "Cross-origin request blocked"}, 403))

        token = request.cookies.get(cfg.SESSION_COOKIE)
        sess = None
        state = None
        if token:
            def _resolve():
                with platform_db() as conn:
                    s = service.resolve_session(conn, token)
                    st = company_state(conn, s["company"]["id"]) if s and s["company"] else None
                    return s, st
            sess, state = await run_in_threadpool(_resolve)
        if sess:
            request.state.user = sess["user"]
            request.state.session = sess
            request.state.company_state = state

        scope = None
        if area != "public":
            if not sess:
                resp = _deny(request, 401, "Not authenticated", f"/login?next={quote(path)}")
                if token:
                    resp.delete_cookie(cfg.SESSION_COOKIE, path="/")
                return _secure_headers(request, resp)
            user = sess["user"]
            role = user["role"]
            home = home_for(user, sess["support_mode"])
            if user["must_change_password"] and path not in PENDING_PW_ALLOWED:
                return _secure_headers(request, _deny(request, 403, "password_change_required", "/account/password"))

            if area == "customer" and role != "customer":
                return _secure_headers(request, _deny(request, 403, "You do not have access to this area", home))
            if area == "console" and role != "superadmin":
                return _secure_headers(request, _deny(request, 403, "You do not have access to this area", home))
            if area == "company":
                in_company = role in ("admin", "employee") or (role == "superadmin" and sess["support_mode"])
                if not in_company or not sess["company"]:
                    return _secure_headers(request, _deny(request, 403, "You do not have access to this area", home))
                if state and state["staff_blocked"] and role != "superadmin":
                    return _secure_headers(request, _deny(request, 403, "company_suspended", "/login"))
                if role == "employee":
                    if path.startswith(ADMIN_ONLY_PREFIX) or path == "/app/admin":
                        return _secure_headers(request, JSONResponse({"detail": "Only company admins can do this"}, 403))
                    if _is_api(path) or path.startswith("/documents/"):
                        ok, action = _employee_allowed(sess, method, path)
                        if not ok:
                            return _secure_headers(request, JSONResponse(
                                {"detail": "permission_denied", "action": action}, 403))
                        if sess["project_ids"] is not None:
                            scope = Scope(sess["project_ids"], resolve_db_path(sess["company"]["db_path"]))
                if (state and state["read_only"] and role != "superadmin" and method not in SAFE_METHODS
                        and path not in READONLY_ALLOWED_WRITES and _action_for(method, path) != "view"):
                    return _secure_headers(request, JSONResponse({"detail": "subscription_expired"}, 402))
            if area == "any" and path.startswith("/documents/") and role == "employee":
                ok, _ = _employee_allowed(sess, method, path)
                if not ok:
                    return _secure_headers(request, JSONResponse({"detail": "Document not found"}, 404))
                if sess["project_ids"] is not None:
                    scope = Scope(sess["project_ids"], resolve_db_path(sess["company"]["db_path"]))

            if method not in SAFE_METHODS:
                sent = request.headers.get("x-csrf-token", "")
                if not hmac.compare_digest(sent, sess["csrf_token"]):
                    return _secure_headers(request, JSONResponse({"detail": "Invalid or missing CSRF token"}, 403))

        # Project scoping for limited employees.
        if scope is not None:
            try:
                scope.check_path(path)
                scope.check_query(dict(parse_qsl(request.url.query)))
                if method not in SAFE_METHODS:
                    raw = await request.body()
                    if raw:
                        try:
                            scope.check_body(json.loads(raw))
                        except ValueError:
                            pass
                if method in SAFE_METHODS:
                    request.scope["query_string"] = scope.scoped_query_string(request.scope.get("query_string", b""))
            except ScopeDenied:
                msg = "Document not found" if path.startswith("/documents/") else "This belongs to a project you are not assigned to"
                return _secure_headers(request, JSONResponse({"detail": msg}, 404 if path.startswith("/documents/") else 403))

        db_token = None
        if sess and sess["company"]:
            db_token = current_db_path.set(resolve_db_path(sess["company"]["db_path"]))
        uid_token = current_user_id.set(sess["user"]["id"] if sess else None)
        ip_token = current_ip.set(client_ip(request))
        try:
            response = await call_next(request)
        finally:
            current_user_id.reset(uid_token)
            current_ip.reset(ip_token)
            if db_token is not None:
                current_db_path.reset(db_token)

        if scope is not None and method in SAFE_METHODS and response.headers.get("content-type", "").startswith("application/json"):
            body = b"".join([chunk async for chunk in response.body_iterator])
            try:
                data = scope.filter_response(path, json.loads(body))
                headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
                response = JSONResponse(data, status_code=response.status_code, headers=headers)
            except ValueError:
                response = Response(body, status_code=response.status_code, headers=dict(response.headers))
        return _secure_headers(request, response)


def set_session_cookie(request: Request, response: Response, token: str) -> None:
    secure = cfg.COOKIE_SECURE == "1" or (cfg.COOKIE_SECURE == "auto" and _is_https(request))
    response.set_cookie(
        cfg.SESSION_COOKIE, token,
        max_age=cfg.SESSION_ABSOLUTE_HOURS * 3600,
        httponly=True, secure=secure, samesite="lax", path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(cfg.SESSION_COOKIE, path="/")
