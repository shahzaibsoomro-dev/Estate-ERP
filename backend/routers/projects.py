from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.database import get_db
from backend.services import projects as svc

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str
    location: str | None = None
    description: str | None = None
    area: str | None = None
    city: str | None = None
    start_date: str | None = None
    expected_end_date: str | None = None
    status: str = "planning"
    current_progress: int = 0
    number_of_floors: int = 0
    number_of_units: int = 0
    project_attributes: list | None = None
    total_area_ghaz: float | None = None
    estimated_cost: int | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    location: str | None = None
    description: str | None = None
    area: str | None = None
    city: str | None = None
    start_date: str | None = None
    expected_end_date: str | None = None
    status: str | None = None
    current_progress: int | None = None
    number_of_floors: int | None = None
    number_of_units: int | None = None
    project_attributes: list | None = None
    total_area_ghaz: float | None = None
    estimated_cost: int | None = None


@router.get("")
def list_projects():
    with get_db() as conn:
        return svc.list_projects(conn)


@router.get("/{project_id}")
def get_project(project_id: int):
    with get_db() as conn:
        p = svc.get_project(conn, project_id)
        if not p:
            raise HTTPException(404, "Project not found")
        return p


@router.post("")
def create_project(body: ProjectCreate):
    with get_db() as conn:
        return svc.create_project(conn, body.model_dump())


@router.put("/{project_id}")
def update_project(project_id: int, body: ProjectUpdate):
    with get_db() as conn:
        p = svc.update_project(conn, project_id, body.model_dump(exclude_unset=True))
        if not p:
            raise HTTPException(404, "Project not found")
        return p
