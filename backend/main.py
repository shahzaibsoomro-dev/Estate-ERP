from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from backend.auth import settings as auth_cfg
from backend.auth.bootstrap import bootstrap_superadmin
from backend.auth.middleware import AuthMiddleware
from backend.config import STATIC_DIR
from backend.saas.service import bootstrap_platform
from backend.routers import (
    accounts,
    agents,
    audit,
    auth,
    bookings,
    budget,
    company,
    console,
    contractors,
    customers,
    dashboard,
    documents,
    entities,
    health,
    holds,
    inventory,
    investors,
    me,
    partners,
    payments,
    portal,
    portal_access,
    possession,
    projects,
    public,
    recovery,
    reports,
    settings,
    setup,
    site_logs,
    stubs,
    units,
    vendors,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    bootstrap_platform()
    bootstrap_superadmin()
    yield


app = FastAPI(title="Haven Builders ERP", lifespan=lifespan)

# Order matters: the last middleware added runs first. Auth must wrap every route.
app.add_middleware(AuthMiddleware)
if auth_cfg.CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=auth_cfg.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )

for mod in (
    health, public, setup, auth, console, company, portal_access, me, documents,
    dashboard, projects, units, customers, bookings, payments,
    recovery, vendors, budget, site_logs, accounts, agents, investors, partners, entities,
    contractors, inventory, possession, settings, portal, audit, reports, stubs,
    holds,
):
    app.include_router(mod.router)

if Path(STATIC_DIR).exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

NO_CACHE = {"Cache-Control": "no-cache, no-store, must-revalidate"}


def _page(name: str):
    path = Path(STATIC_DIR) / name
    if path.exists():
        return FileResponse(path, headers=NO_CACHE)
    return HTMLResponse("Not found", status_code=404)


@app.get("/", include_in_schema=False)
def home():
    return _page("home.html")


@app.get("/setup", include_in_schema=False)
def setup_page():
    return _page("setup.html")


@app.get("/login", include_in_schema=False)
def login_page():
    return _page("login.html")


@app.get("/account/password", include_in_schema=False)
def password_page():
    return _page("login.html")


@app.get("/app", include_in_schema=False)
def admin_app():
    return _page("index.html")


@app.get("/console", include_in_schema=False)
def console_page():
    return _page("console.html")


@app.get("/c/{slug}", include_in_schema=False)
def company_home(slug: str):
    return _page("home.html")


@app.get("/portal", include_in_schema=False)
def customer_portal():
    return _page("portal.html")


@app.get("/robots.txt", include_in_schema=False)
def robots():
    return HTMLResponse("User-agent: *\nAllow: /$\nDisallow: /app\nDisallow: /portal\nDisallow: /api/\nDisallow: /documents/\n",
                        media_type="text/plain")
