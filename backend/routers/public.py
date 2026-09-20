"""Unauthenticated data for the homepage — only non-sensitive project information."""
import json

from fastapi import APIRouter, HTTPException

from backend.database import fetch_all, fetch_one, get_db, platform_db
from backend.saas.service import default_company_id, get_company, resolve_db_path

router = APIRouter(prefix="/api/public", tags=["public"])


@router.get("/overview")
def overview(company: str | None = None):
    with platform_db() as pconn:
        if company:
            row = fetch_one(pconn, "SELECT id FROM companies WHERE slug=? AND status='active'", (company,))
            cid = row["id"] if row else None
        else:
            cid = default_company_id(pconn)
        c = get_company(pconn, cid) if cid else None
    if not c:
        raise HTTPException(404, "Company not found")
    with get_db(resolve_db_path(c["db_path"])) as conn:
        projects = fetch_all(
            conn,
            """SELECT p.id, p.name, p.city, p.area, p.location, p.status, p.current_progress,
                      p.number_of_floors, p.project_attributes, p.expected_end_date,
                      SUM(CASE WHEN u.status='available' THEN 1 ELSE 0 END) AS available_units,
                      COUNT(u.id) AS total_units,
                      MIN(CASE WHEN u.status='available' THEN u.base_sale_price END) AS price_from,
                      GROUP_CONCAT(DISTINCT u.unit_type) AS unit_types
               FROM projects p LEFT JOIN units u ON u.project_id=p.id
               WHERE COALESCE(p.is_public, 1) = 1
               GROUP BY p.id HAVING total_units > 0
               ORDER BY CASE p.status WHEN 'under_construction' THEN 0 WHEN 'planning' THEN 1 ELSE 2 END, p.name""",
        )
        for p in projects:
            try:
                p["attributes"] = json.loads(p.pop("project_attributes") or "[]")
            except ValueError:
                p["attributes"] = []
            raw_types = [t.strip() for t in (p["unit_types"] or "").split(",") if t and t.strip()]
            labels = []
            for t in raw_types:
                key = t.lower()
                if key in ("commercial", "shop", "office", "showroom", "warehouse"):
                    label = "Commercial"
                else:
                    label = "Residential"
                if label not in labels:
                    labels.append(label)
            p["unit_types"] = labels
        name = fetch_one(conn, "SELECT value FROM company_settings WHERE key='company_name'")
        phone = fetch_one(conn, "SELECT value FROM company_settings WHERE key='company_phone'")
        email = fetch_one(conn, "SELECT value FROM company_settings WHERE key='company_email'")
        delivered = fetch_one(conn, "SELECT COUNT(*) n FROM units WHERE status IN ('delivered','possession_delivered')")
        return {
            "company": {"name": name["value"] if name else c["name"], "slug": c["slug"],
                        "phone": phone["value"] if phone else "", "email": email["value"] if email else ""},
            "stats": {
                "projects": len(projects),
                "cities": len({p["city"] for p in projects if p["city"]}),
                "units": sum(p["total_units"] for p in projects),
                "delivered": delivered["n"] if delivered else 0,
            },
            "projects": projects,
        }
