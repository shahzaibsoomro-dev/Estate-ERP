from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from backend.auth.deps import current_user, require_staff
from backend.database import get_db
from backend.documents import render as r
from backend.documents import service as svc

router = APIRouter(tags=["documents"])
staff = [Depends(require_staff)]


class TemplateBody(BaseModel):
    name: str = Field(max_length=120)
    kind: str = Field("general", max_length=40)
    description: str | None = Field(None, max_length=500)
    body_html: str = Field(max_length=200_000)
    requires_booking: bool = True
    is_active: bool = True


class PreviewBody(BaseModel):
    template_id: int | None = None
    body_html: str | None = Field(None, max_length=200_000)
    customer_id: int
    booking_id: int | None = None


class GenerateBody(BaseModel):
    template_id: int
    customer_id: int
    booking_id: int | None = None
    title: str | None = Field(None, max_length=160)
    visible_to_customer: bool = True


class DocUpdate(BaseModel):
    visible_to_customer: bool | None = None
    revoke: bool = False


def _err(e: Exception) -> HTTPException:
    return HTTPException(404 if isinstance(e, LookupError) else 400, str(e))


@router.get("/api/document-templates", dependencies=staff)
def list_templates():
    with get_db() as conn:
        return {"templates": svc.list_templates(conn), "fields": r.FIELDS}


@router.get("/api/document-templates/{template_id}", dependencies=staff)
def get_template(template_id: int):
    with get_db() as conn:
        t = svc.get_template(conn, template_id)
        if not t:
            raise HTTPException(404, "Template not found")
        return t


@router.post("/api/document-templates")
def create_template(body: TemplateBody, user: dict = Depends(require_staff)):
    with get_db() as conn:
        try:
            return svc.save_template(conn, None, **body.model_dump(), user_id=user["id"])
        except (ValueError, LookupError) as e:
            raise _err(e) from e


@router.put("/api/document-templates/{template_id}")
def update_template(template_id: int, body: TemplateBody, user: dict = Depends(require_staff)):
    with get_db() as conn:
        try:
            return svc.save_template(conn, template_id, **body.model_dump(), user_id=user["id"])
        except (ValueError, LookupError) as e:
            raise _err(e) from e


@router.post("/api/document-templates/preview", dependencies=staff)
def preview(body: PreviewBody):
    with get_db() as conn:
        try:
            return {"html": svc.preview(conn, body.template_id, body.body_html, body.customer_id, body.booking_id)}
        except (ValueError, LookupError) as e:
            raise _err(e) from e


@router.get("/api/customer-documents", dependencies=staff)
def list_documents(customer_id: int | None = None):
    with get_db() as conn:
        return svc.list_documents(conn, customer_id)


@router.post("/api/customer-documents")
def generate(body: GenerateBody, user: dict = Depends(require_staff)):
    with get_db() as conn:
        try:
            doc = svc.generate(conn, **body.model_dump(), user_id=user["id"])
        except (ValueError, LookupError) as e:
            raise _err(e) from e
        doc.pop("body_html", None)
        return doc


@router.patch("/api/customer-documents/{doc_id}", dependencies=staff)
def update_document(doc_id: int, body: DocUpdate):
    with get_db() as conn:
        try:
            doc = svc.update_document(conn, doc_id, visible_to_customer=body.visible_to_customer, revoke=body.revoke)
        except LookupError as e:
            raise _err(e) from e
        doc.pop("body_html", None)
        return doc


@router.get("/documents/{doc_id}", response_class=HTMLResponse)
def view_document(doc_id: int, request: Request):
    """Printable page. Staff can open any document; customers only their own visible ones."""
    user = current_user(request)
    with get_db() as conn:
        doc = svc.get_document(conn, doc_id)
    sess = request.state.session
    is_staff = user["role"] in ("admin", "employee") or (user["role"] == "superadmin" and sess["support_mode"])
    allowed = doc and (is_staff or (
        user["role"] == "customer" and doc["customer_id"] == user.get("customer_id")
        and doc["visible_to_customer"] and not doc["revoked_at"]
    ))
    if not allowed:
        # Same response for "missing" and "not yours" so ids can't be probed.
        raise HTTPException(404, "Document not found")
    back = "/app#documents" if is_staff else "/portal#documents"
    body = doc["body_html"]
    if doc["revoked_at"]:
        body = '<p style="background:#FEF2F2;color:#B91C1C;padding:8px 12px;border-radius:6px"><b>Revoked</b> — this document is no longer valid.</p>' + body
    return HTMLResponse(r.page_html(doc["title"], doc["doc_no"], body, back),
                        headers={"X-Robots-Tag": "noindex"})
