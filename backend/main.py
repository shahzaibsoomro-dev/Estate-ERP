from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.config import STATIC_DIR
from backend.db.seed import init_db
from backend.routers import (
    agents,
    bookings,
    budget,
    customers,
    dashboard,
    health,
    investors,
    payments,
    projects,
    recovery,
    settings,
    stubs,
    units,
    vendors,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Haven Builders ERP", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

for mod in (
    health, dashboard, projects, units, customers, bookings, payments,
    recovery, vendors, budget, agents, investors, settings, stubs,
):
    app.include_router(mod.router)

if Path(STATIC_DIR).exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    index_path = Path(STATIC_DIR) / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "Haven Builders ERP API"}
