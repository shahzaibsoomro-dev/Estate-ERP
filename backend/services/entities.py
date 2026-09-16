"""Unified party / entity master: one place for id + all related records."""

from backend.database import fetch_all, fetch_one
from backend.services import agents as agents_svc
from backend.services import contractors as contractors_svc
from backend.services import customers as customers_svc
from backend.services import investors as investors_svc
from backend.services import partners as partners_svc
from backend.services import vendors as vendors_svc

ENTITY_META = {
    "customer": {"prefix": "CUS", "label": "Customer"},
    "vendor": {"prefix": "VEN", "label": "Vendor"},
    "agent": {"prefix": "AGT", "label": "Agent"},
    "investor": {"prefix": "INV", "label": "Investor"},
    "partner": {"prefix": "PAR", "label": "Partner"},
    "contractor": {"prefix": "CTR", "label": "Contractor"},
}


def master_id(entity_type: str, entity_id: int) -> str:
    meta = ENTITY_META.get(entity_type)
    if not meta:
        return str(entity_id)
    return f"{meta['prefix']}-{entity_id}"


def list_entities(conn, q: str | None = None, entity_type: str | None = None) -> list[dict]:
    needle = (q or "").strip().lower()
    types = [entity_type] if entity_type in ENTITY_META else list(ENTITY_META.keys())
    rows: list[dict] = []

    if "customer" in types:
        for c in fetch_all(conn, "SELECT id, name, cnic, contact_number FROM customers ORDER BY name"):
            rows.append({
                "entity_type": "customer",
                "entity_id": c["id"],
                "master_id": master_id("customer", c["id"]),
                "name": c["name"],
                "subtitle": c.get("contact_number") or c.get("cnic"),
                "status": "active",
            })
    if "vendor" in types:
        for v in fetch_all(conn, "SELECT id, name, contact, category, ntn, status FROM vendors ORDER BY name"):
            rows.append({
                "entity_type": "vendor",
                "entity_id": v["id"],
                "master_id": master_id("vendor", v["id"]),
                "name": v["name"],
                "subtitle": " · ".join(x for x in [v.get("category"), v.get("ntn"), v.get("contact")] if x),
                "status": v.get("status") or "active",
            })
    if "agent" in types:
        for a in fetch_all(conn, "SELECT id, name, contact, category, status FROM agents ORDER BY name"):
            rows.append({
                "entity_type": "agent",
                "entity_id": a["id"],
                "master_id": master_id("agent", a["id"]),
                "name": a["name"],
                "subtitle": " · ".join(x for x in [a.get("category"), a.get("contact")] if x),
                "status": a.get("status") or "active",
            })
    if "investor" in types:
        for i in fetch_all(conn, "SELECT id, name, mobile_number, cnic, email, status FROM investors ORDER BY name"):
            rows.append({
                "entity_type": "investor",
                "entity_id": i["id"],
                "master_id": master_id("investor", i["id"]),
                "name": i["name"],
                "subtitle": " · ".join(x for x in [i.get("mobile_number"), i.get("cnic")] if x),
                "status": i.get("status") or "active",
            })
    if "partner" in types:
        try:
            partners = fetch_all(conn, "SELECT id, name, mobile_number, cnic, email, status FROM partners ORDER BY name")
        except Exception:
            partners = []
        for p in partners:
            rows.append({
                "entity_type": "partner",
                "entity_id": p["id"],
                "master_id": master_id("partner", p["id"]),
                "name": p["name"],
                "subtitle": " · ".join(x for x in [p.get("mobile_number"), p.get("cnic")] if x),
                "status": p.get("status") or "active",
            })
    if "contractor" in types:
        try:
            contractors = fetch_all(
                conn, "SELECT id, name, contact, specialty, ntn, status FROM contractors ORDER BY name"
            )
        except Exception:
            contractors = []
        for c in contractors:
            rows.append({
                "entity_type": "contractor",
                "entity_id": c["id"],
                "master_id": master_id("contractor", c["id"]),
                "name": c["name"],
                "subtitle": " · ".join(x for x in [c.get("specialty"), c.get("ntn"), c.get("contact")] if x),
                "status": c.get("status") or "active",
            })

    if needle:
        rows = [
            r for r in rows
            if needle in " ".join([
                r.get("master_id") or "",
                r.get("name") or "",
                r.get("subtitle") or "",
                r.get("entity_type") or "",
            ]).lower()
        ]
    rows.sort(key=lambda r: ((r.get("name") or "").lower(), r.get("entity_type") or "", r.get("entity_id") or 0))
    return rows


def _timeline_sort(items: list[dict]) -> list[dict]:
    items.sort(key=lambda x: (x.get("date") or "", x.get("kind") or ""), reverse=True)
    return items


def get_entity(conn, entity_type: str, entity_id: int) -> dict | None:
    if entity_type not in ENTITY_META:
        raise ValueError("Unknown entity type")
    mid = master_id(entity_type, entity_id)
    meta = ENTITY_META[entity_type]

    if entity_type == "customer":
        person = customers_svc.get_customer(conn, entity_id)
        if not person:
            return None
        holds = fetch_all(
            conn,
            """SELECT h.*, u.unit_no, p.name AS project_name
               FROM unit_holds h
               JOIN units u ON u.id=h.unit_id
               JOIN projects p ON p.id=u.project_id
               WHERE h.customer_id=?
               ORDER BY h.id DESC""",
            (entity_id,),
        )
        timeline = []
        for pay in person.get("payments") or []:
            timeline.append({
                "date": pay.get("payment_date"), "kind": "payment",
                "direction": "in", "amount": pay.get("amount"),
                "label": f"Payment · {pay.get('receipt_no') or pay.get('unit_no') or ''}",
                "ref": pay.get("receipt_no"),
            })
        for h in holds:
            timeline.append({
                "date": h.get("held_at"), "kind": "hold",
                "direction": "info", "amount": h.get("token_amount") or 0,
                "label": f"Hold · {h.get('unit_no')} ({h.get('status')})",
                "ref": None,
            })
        return {
            "entity_type": entity_type, "entity_id": entity_id, "master_id": mid,
            "label": meta["label"], "name": person.get("name"), "status": person.get("status") or "active",
            "profile": person, "holds": holds, "timeline": _timeline_sort(timeline),
        }

    if entity_type == "vendor":
        person = vendors_svc.get_vendor(conn, entity_id)
        if not person:
            return None
        person["master_id"] = mid
        timeline = []
        for po in person.get("purchase_orders") or []:
            timeline.append({
                "date": po.get("order_date"), "kind": "po",
                "direction": "info", "amount": po.get("total"),
                "label": f"PO · {po.get('po_no')} · {po.get('project_name') or ''}",
                "ref": po.get("po_no"),
            })
        for pay in person.get("payments") or []:
            timeline.append({
                "date": pay.get("payment_date"), "kind": "payment",
                "direction": "out", "amount": pay.get("amount"),
                "label": f"Vendor payment · {pay.get('po_no') or ''}",
                "ref": pay.get("reference_number"),
            })
        return {
            "entity_type": entity_type, "entity_id": entity_id, "master_id": mid,
            "label": meta["label"], "name": person.get("name"), "status": person.get("status"),
            "profile": person, "timeline": _timeline_sort(timeline),
        }

    if entity_type == "agent":
        person = agents_svc.get_agent(conn, entity_id)
        if not person:
            return None
        timeline = []
        for p in person.get("payments") or []:
            timeline.append({
                "date": p.get("payment_date"), "kind": "commission_payment",
                "direction": "out", "amount": p.get("amount"),
                "label": f"Commission paid · {p.get('booking_no') or ''}",
                "ref": None,
            })
        for b in person.get("bonuses") or []:
            timeline.append({
                "date": b.get("bonus_date"), "kind": "bonus",
                "direction": "out", "amount": b.get("amount"),
                "label": f"Bonus · {b.get('reason') or 'Performance'}",
                "ref": None,
            })
        for c in person.get("commissions") or []:
            timeline.append({
                "date": None, "kind": "commission",
                "direction": "info", "amount": c.get("commission_amount"),
                "label": f"Commission earned · {c.get('booking_no') or ''}",
                "ref": c.get("booking_no"),
            })
        return {
            "entity_type": entity_type, "entity_id": entity_id, "master_id": mid,
            "label": meta["label"], "name": person.get("name"), "status": person.get("status"),
            "profile": person, "timeline": _timeline_sort(timeline),
        }

    if entity_type == "investor":
        person = investors_svc.get_investor(conn, entity_id)
        if not person:
            return None
        person["master_id"] = mid
        timeline = []
        for c in person.get("contributions") or []:
            timeline.append({
                "date": c.get("contribution_date"), "kind": "contribution",
                "direction": "in", "amount": c.get("amount"),
                "label": "Investment in", "ref": None,
            })
        for d in person.get("distributions") or []:
            timeline.append({
                "date": d.get("distribution_date"), "kind": "distribution",
                "direction": "out", "amount": d.get("amount"),
                "label": "Return / distribution", "ref": None,
            })
        return {
            "entity_type": entity_type, "entity_id": entity_id, "master_id": mid,
            "label": meta["label"], "name": person.get("name"), "status": person.get("status"),
            "profile": person, "timeline": _timeline_sort(timeline),
        }

    if entity_type == "partner":
        person = partners_svc.get_partner(conn, entity_id)
        if not person:
            return None
        person["master_id"] = mid
        timeline = []
        for c in person.get("contributions") or []:
            timeline.append({
                "date": c.get("contribution_date"), "kind": "contribution",
                "direction": "in", "amount": c.get("amount"),
                "label": "Partner capital in", "ref": None,
            })
        for d in person.get("distributions") or []:
            timeline.append({
                "date": d.get("distribution_date"), "kind": "distribution",
                "direction": "out", "amount": d.get("amount"),
                "label": "Partner distribution", "ref": None,
            })
        return {
            "entity_type": entity_type, "entity_id": entity_id, "master_id": mid,
            "label": meta["label"], "name": person.get("name"), "status": person.get("status"),
            "profile": person, "timeline": _timeline_sort(timeline),
        }

    if entity_type == "contractor":
        person = contractors_svc.get_contractor(conn, entity_id)
        if not person:
            return None
        timeline = []
        for a in person.get("assignments") or []:
            timeline.append({
                "date": a.get("start_date"), "kind": "assignment",
                "direction": "info", "amount": a.get("contract_amount"),
                "label": f"Assigned · {a.get('project_name') or ''} · {a.get('role') or ''}",
                "ref": a.get("project_name"),
            })
        for p in person.get("payments") or []:
            timeline.append({
                "date": p.get("payment_date"), "kind": "payment",
                "direction": "out", "amount": p.get("amount"),
                "label": f"Contractor payment · {p.get('project_name') or ''}",
                "ref": p.get("reference_number"),
            })
        return {
            "entity_type": entity_type, "entity_id": entity_id, "master_id": mid,
            "label": meta["label"], "name": person.get("name"), "status": person.get("status"),
            "profile": person, "timeline": _timeline_sort(timeline),
        }

    return None
