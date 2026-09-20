from fastapi import Request, APIRouter, HTTPException
from pydantic import BaseModel
from backend.database import get_db
from backend.services import installment_templates as tmpl_svc
from backend.services import projects as svc

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("/pay-plans")
def list_pay_plans():
    with get_db() as conn:
        return tmpl_svc.list_pay_plans(conn)


class ProjectCreate(BaseModel):
    name: str
    location: str | None = None
    description: str | None = None
    area: str | None = None
    city: str | None = None
    start_date: str | None = None
    expected_end_date: str | None = None
    status: str = "planning"
    project_type: str = "building"
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
    project_type: str | None = None
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
def create_project(body: ProjectCreate, request: Request):
    sess = getattr(request.state, "session", None)
    if sess and sess.get("project_ids") is not None:
        raise HTTPException(403, "Only staff with access to all projects can create projects")
    with get_db() as conn:
        if sess and sess.get("company"):
            from backend.database import platform_db
            from backend.saas.service import check_limit
            count = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
            with platform_db() as pconn:
                try:
                    check_limit(pconn, sess["company"]["id"], "projects", count)
                except ValueError as e:
                    raise HTTPException(400, str(e)) from e
        try:
            return svc.create_project(conn, body.model_dump())
        except ValueError as e:
            raise HTTPException(400, str(e)) from e


@router.put("/{project_id}")
def update_project(project_id: int, body: ProjectUpdate):
    with get_db() as conn:
        try:
            p = svc.update_project(conn, project_id, body.model_dump(exclude_unset=True))
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        if not p:
            raise HTTPException(404, "Project not found")
        return p


@router.delete("/{project_id}")
def delete_project(project_id: int):
    with get_db() as conn:
        try:
            svc.delete_project(conn, project_id)
            return {"ok": True}
        except ValueError as e:
            raise HTTPException(400, str(e)) from e


class TemplateRule(BaseModel):
    label: str
    amount_bps: int
    trigger_kind: str = "construction"
    milestone_progress: int | None = None
    trigger_progress: int | None = None
    forecast_due_date: str | None = None
    due_days_after_trigger: int = 0
    installment_count: int = 1
    start_offset_months: int = 0
    interval_months: int = 1
    notes: str | None = None


class TemplateBody(BaseModel):
    name: str = "Construction installment plan"
    default_booking_bps: int = 1000
    rules: list[TemplateRule]


class TemplatePreviewBody(BaseModel):
    booking_date: str | None = None
    sale_price: int
    booking_amount: int = 0
    template_id: int | None = None


@router.get("/{project_id}/installment-template")
def get_installment_template(project_id: int):
    with get_db() as conn:
        tmpl = tmpl_svc.get_active_template(conn, project_id)
        return tmpl or {"rules": [], "is_active": 0}


@router.put("/{project_id}/installment-template")
def put_installment_template(project_id: int, body: TemplateBody):
    with get_db() as conn:
        try:
            return tmpl_svc.save_template(conn, project_id, body.model_dump())
        except ValueError as e:
            raise HTTPException(400, str(e)) from e


@router.delete("/{project_id}/installment-template")
def delete_installment_template(project_id: int):
    with get_db() as conn:
        tmpl_svc.delete_active_template(conn, project_id)
        return {"ok": True}


@router.post("/{project_id}/installment-template/preview")
def preview_installment_template(project_id: int, body: TemplatePreviewBody):
    with get_db() as conn:
        try:
            return tmpl_svc.preview_plan(
                conn, project_id, body.sale_price, body.booking_amount, body.template_id, body.booking_date,
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
