"""Document templates and generated customer documents."""
from backend.database import fetch_all, fetch_one
from backend.documents import render as r
from backend.services import audit

TEMPLATE_COLS = "id, code, name, kind, description, requires_booking, is_active, created_at, updated_at"


def list_templates(conn, include_inactive: bool = True) -> list[dict]:
    sql = f"SELECT {TEMPLATE_COLS} FROM document_templates"
    if not include_inactive:
        sql += " WHERE is_active=1"
    return fetch_all(conn, sql + " ORDER BY is_active DESC, name")


def get_template(conn, template_id: int) -> dict | None:
    return fetch_one(conn, f"SELECT {TEMPLATE_COLS}, body_html FROM document_templates WHERE id=?", (template_id,))


def _check(name: str, body_html: str, requires_booking: bool) -> None:
    if not (name or "").strip():
        raise ValueError("Template name is required")
    problems = r.template_problems(body_html or "")
    if problems:
        raise ValueError("; ".join(problems))
    if not requires_booking:
        used = set(r.PLACEHOLDER_RE.findall(body_html))
        if used & r.BOOKING_KEYS:
            raise ValueError("This template uses booking fields, so it must require a booking")


def save_template(conn, template_id: int | None, *, name: str, kind: str, description: str | None,
                  body_html: str, requires_booking: bool, is_active: bool, user_id: int | None) -> dict:
    _check(name, body_html, requires_booking)
    if template_id is None:
        cur = conn.execute(
            """INSERT INTO document_templates(name, kind, description, body_html, requires_booking, is_active, created_by)
               VALUES(?,?,?,?,?,?,?)""",
            (name.strip(), kind or "general", description, body_html, int(requires_booking), int(is_active), user_id),
        )
        template_id = cur.lastrowid
        audit.log(conn, "document_template", template_id, "create", {"name": name})
    else:
        if not get_template(conn, template_id):
            raise LookupError("Template not found")
        conn.execute(
            """UPDATE document_templates SET name=?, kind=?, description=?, body_html=?, requires_booking=?,
                      is_active=?, updated_at=datetime('now') WHERE id=?""",
            (name.strip(), kind or "general", description, body_html, int(requires_booking), int(is_active), template_id),
        )
        audit.log(conn, "document_template", template_id, "update", {"name": name})
    return get_template(conn, template_id)


def _next_doc_no(conn) -> str:
    row = fetch_one(conn, "SELECT MAX(CAST(SUBSTR(doc_no, 5) AS INTEGER)) AS n FROM customer_documents WHERE doc_no LIKE 'DOC-%'")
    return f"DOC-{(row['n'] or 0) + 1:05d}"


def preview(conn, template_id: int | None, body_html: str | None, customer_id: int, booking_id: int | None) -> str:
    if body_html is None:
        t = get_template(conn, template_id) if template_id else None
        if not t:
            raise LookupError("Template not found")
        body_html = t["body_html"]
    problems = r.template_problems(body_html)
    if problems:
        raise ValueError("; ".join(problems))
    ctx = r.build_context(conn, customer_id, booking_id)
    ctx["values"].update({"doc.no": "PREVIEW", "doc.title": "Preview"})
    return r.render(body_html, ctx)


def generate(conn, *, template_id: int, customer_id: int, booking_id: int | None,
             title: str | None, visible_to_customer: bool, user_id: int | None) -> dict:
    t = get_template(conn, template_id)
    if not t or not t["is_active"]:
        raise LookupError("Template not found or inactive")
    if t["requires_booking"] and not booking_id:
        raise ValueError("Choose a booking for this template")
    ctx = r.build_context(conn, customer_id, booking_id)
    doc_no = _next_doc_no(conn)
    title = (title or "").strip() or t["name"]
    ctx["values"].update({"doc.no": doc_no, "doc.title": title})
    body = r.render(t["body_html"], ctx)
    cur = conn.execute(
        """INSERT INTO customer_documents(doc_no, customer_id, booking_id, template_id, title, body_html,
                                          visible_to_customer, created_by)
           VALUES(?,?,?,?,?,?,?,?)""",
        (doc_no, customer_id, booking_id, template_id, title, body, int(visible_to_customer), user_id),
    )
    audit.log(conn, "customer_document", cur.lastrowid, "generate",
              {"doc_no": doc_no, "customer_id": customer_id, "template": t["name"]})
    return get_document(conn, cur.lastrowid)


DOC_LIST_COLS = """d.id, d.doc_no, d.customer_id, d.booking_id, d.template_id, d.title,
                   d.visible_to_customer, d.created_at, d.revoked_at,
                   c.name AS customer_name, b.booking_no, u.unit_no, p.name AS project_name,
                   t.kind, d.created_by"""
DOC_JOINS = """FROM customer_documents d
               JOIN customers c ON c.id=d.customer_id
               LEFT JOIN bookings b ON b.id=d.booking_id
               LEFT JOIN units u ON u.id=b.unit_id
               LEFT JOIN projects p ON p.id=b.project_id
               LEFT JOIN document_templates t ON t.id=d.template_id"""


def list_documents(conn, customer_id: int | None = None, customer_view: bool = False) -> list[dict]:
    where, params = [], []
    if customer_id is not None:
        where.append("d.customer_id=?")
        params.append(customer_id)
    if customer_view:
        where.append("d.visible_to_customer=1 AND d.revoked_at IS NULL")
    sql = f"SELECT {DOC_LIST_COLS} {DOC_JOINS}"
    if where:
        sql += " WHERE " + " AND ".join(where)
    rows = fetch_all(conn, sql + " ORDER BY d.created_at DESC, d.id DESC LIMIT 500", tuple(params))
    if customer_view:
        for row in rows:
            row.pop("created_by", None)
    else:
        _attach_author_names(rows)
    return rows


def _attach_author_names(rows: list[dict]) -> None:
    from backend.database import platform_db
    ids = sorted({r["created_by"] for r in rows if r.get("created_by")})
    names = {}
    if ids:
        with platform_db() as pconn:
            names = {r["id"]: r["name"] for r in fetch_all(
                pconn, f"SELECT id, name FROM users WHERE id IN ({','.join('?' * len(ids))})", tuple(ids))}
    for r in rows:
        r["created_by_name"] = names.get(r.get("created_by"), "")


def get_document(conn, doc_id: int) -> dict | None:
    return fetch_one(conn, f"SELECT {DOC_LIST_COLS}, d.body_html {DOC_JOINS} WHERE d.id=?", (doc_id,))


def update_document(conn, doc_id: int, *, visible_to_customer: bool | None = None, revoke: bool = False) -> dict:
    if not get_document(conn, doc_id):
        raise LookupError("Document not found")
    if visible_to_customer is not None:
        conn.execute("UPDATE customer_documents SET visible_to_customer=? WHERE id=?", (int(visible_to_customer), doc_id))
    if revoke:
        conn.execute("UPDATE customer_documents SET revoked_at=datetime('now'), visible_to_customer=0 WHERE id=?", (doc_id,))
    audit.log(conn, "customer_document", doc_id, "revoke" if revoke else "update",
              {"visible_to_customer": visible_to_customer})
    return get_document(conn, doc_id)
