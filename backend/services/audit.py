"""Company activity log — who changed what, with a readable summary for the Activity screen."""
import json
from backend.auth.context import current_ip, current_user_id
from backend.database import execute, fetch_all, fetch_one, platform_db

ENTITY_LABELS = {
    "booking": "Booking",
    "payment": "Payment",
    "unit": "Unit",
    "unit_hold": "Unit hold",
    "purchase_order": "Purchase order",
    "vendor_payment": "Vendor payment",
    "vendor": "Vendor",
    "agent": "Agent",
    "contractor": "Contractor",
    "inventory_item": "Material",
    "investor": "Investor",
    "partner": "Partner",
    "project": "Project",
    "project_stage": "Work stage",
    "project_task": "Work task",
    "boq_line": "BOQ line",
    "budget_line": "Budget line",
    "customer": "Customer",
    "possession_checklist": "Possession",
    "document_template": "Doc template",
    "customer_document": "Document",
    "site_log": "Site log",
}

ACTION_LABELS = {
    "created": "Created",
    "updated": "Updated",
    "deleted": "Deleted",
    "removed": "Removed",
    "recorded": "Recorded",
    "cancelled": "Cancelled",
    "transferred": "Transferred",
    "status": "Status changed",
    "possession": "Possession handed over",
    "converted": "Converted to booking",
    "released": "Released",
    "forfeited": "Forfeited",
    "expired": "Expired",
    "payment": "Payment made",
    "bonus": "Bonus paid",
    "contribution": "Contribution received",
    "distribution": "Distribution paid",
    "assigned": "Assigned to project",
    "movement": "Stock moved",
    "started": "Started",
    "completed": "Completed",
    "generate": "Generated",
    "revoke": "Revoked",
    "update": "Updated",
    "create": "Created",
    "progress": "Progress updated",
    "rescheduled": "Rescheduled",
}

MODULE_BY_ENTITY = {
    "booking": "Sales",
    "payment": "Sales",
    "unit": "Inventory",
    "unit_hold": "Sales",
    "customer": "Sales",
    "purchase_order": "Procurement",
    "vendor_payment": "Procurement",
    "vendor": "Procurement",
    "agent": "Stakeholders",
    "contractor": "Construction",
    "inventory_item": "Construction",
    "site_log": "Construction",
    "investor": "Investment",
    "partner": "Investment",
    "project": "Projects",
    "project_stage": "Planning",
    "project_task": "Planning",
    "boq_line": "Planning",
    "budget_line": "Planning",
    "possession_checklist": "Sales",
    "document_template": "Documents",
    "customer_document": "Documents",
}

_AMOUNT_KEYS = (
    "amount", "token_amount", "token_applied", "transfer_fee", "forfeit", "refund",
    "fee", "sale_price", "planned_amount", "labour_cost",
)


def log(conn, entity_type: str, entity_id: int | None, action: str, details: dict | None = None,
        user_id: int | None = None):
    execute(
        conn,
        "INSERT INTO audit_log(entity_type, entity_id, action, details, user_id, ip) VALUES(?,?,?,?,?,?)",
        (entity_type, entity_id, action, json.dumps(details or {}, default=str),
         user_id if user_id is not None else current_user_id.get(), current_ip.get()),
    )


def parse_details(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {"note": data}
        except (json.JSONDecodeError, TypeError):
            return {"note": raw}
    return {}


def entity_label(entity_type: str) -> str:
    return ENTITY_LABELS.get(entity_type, (entity_type or "Record").replace("_", " ").title())


def action_label(action: str) -> str:
    return ACTION_LABELS.get(action, (action or "Changed").replace("_", " ").title())


def module_for(entity_type: str) -> str:
    return MODULE_BY_ENTITY.get(entity_type, "Other")


def _money(v) -> str | None:
    if v is None or v == "":
        return None
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    return f"PKR {n:,}"


def _pick_amount(details: dict) -> int | None:
    for key in _AMOUNT_KEYS:
        if key in details and details[key] not in (None, ""):
            try:
                return int(details[key])
            except (TypeError, ValueError):
                continue
    return None


def _ref(details: dict, entity_type: str, entity_id) -> str | None:
    for key in ("booking_no", "receipt_no", "po_no", "doc_no", "unit_no", "name"):
        if details.get(key):
            return str(details[key])
    if entity_id is not None:
        return f"{entity_label(entity_type)} #{entity_id}"
    return None


def summarize(entity_type: str, action: str, details: dict, entity_id=None) -> str:
    """One plain-English line for the Activity Log."""
    d = details or {}
    et = entity_label(entity_type)
    act = action_label(action)
    name = d.get("name") or d.get("booking_no") or d.get("po_no") or d.get("unit_no")
    amount = _money(_pick_amount(d))
    project = d.get("project_name")
    customer = d.get("customer_name")
    unit = d.get("unit_no") or (f"unit #{d['unit_id']}" if d.get("unit_id") else None)

    if entity_type == "booking" and action == "created":
        parts = [f"Booked {unit or 'a unit'}"]
        if customer:
            parts.append(f"for {customer}")
        price = _money(d.get("sale_price") or d.get("amount"))
        if price:
            parts.append(f"at {price}")
        if d.get("booking_no"):
            parts.append(f"({d['booking_no']})")
        return " ".join(parts)

    if entity_type == "booking" and action == "cancelled":
        bits = [f"Cancelled booking {d.get('booking_no') or (f'#{entity_id}' if entity_id else '')}".strip()]
        if customer:
            bits.append(f"({customer})")
        money_bits = []
        if d.get("forfeit") is not None:
            money_bits.append(f"forfeit {_money(d['forfeit'])}")
        if d.get("refund") is not None:
            money_bits.append(f"refund {_money(d['refund'])}")
        if money_bits:
            bits.append("— " + ", ".join(money_bits))
        if d.get("reason"):
            bits.append(f"· {d['reason']}")
        return " ".join(bits)

    if entity_type == "booking" and action == "transferred":
        who = f" from {d['from_customer']}" if d.get("from_customer") else ""
        to = f" to {d['to_customer']}" if d.get("to_customer") else ""
        fee = f" (fee {amount})" if amount else ""
        return f"Transferred booking{who}{to}{fee}".strip()

    if entity_type == "payment" and action == "recorded":
        bits = [f"Received {amount or 'a payment'}"]
        if customer:
            bits.append(f"from {customer}")
        if d.get("receipt_no"):
            bits.append(f"· receipt {d['receipt_no']}")
        if unit:
            bits.append(f"· {unit}")
        return " ".join(bits)

    if entity_type == "unit" and action == "status":
        return f"Unit {unit or (f'#{entity_id}' if entity_id else '')} marked {d.get('status', 'updated')}".strip()

    if entity_type == "unit" and action == "possession":
        when = d.get("possession_date") or ""
        return f"Possession handed over for {unit or f'unit #{entity_id}'}" + (f" on {when}" if when else "")

    if entity_type == "unit_hold" and action == "created":
        bits = [f"Hold placed on {unit or 'a unit'}"]
        if customer:
            bits.append(f"for {customer}")
        if amount:
            bits.append(f"· token {amount}")
        return " ".join(bits)

    if entity_type == "unit_hold" and action in ("released", "forfeited", "expired", "converted"):
        verb = {
            "released": "Hold released", "forfeited": "Hold forfeited",
            "expired": "Hold expired", "converted": "Hold converted to booking",
        }[action]
        bits = [verb]
        if unit:
            bits.append(f"on {unit}")
        if amount and action != "converted":
            bits.append(f"· refund {amount}")
        if action == "converted" and d.get("booking_id"):
            bits.append(f"· booking #{d['booking_id']}")
        return " ".join(bits)

    if entity_type == "purchase_order" and action == "cancelled":
        bits = [f"Cancelled PO {d.get('po_no') or f'#{entity_id}'}"]
        if d.get("fee") is not None or d.get("refund") is not None:
            bits.append(f"· fee {_money(d.get('fee'))}, refund {_money(d.get('refund'))}")
        return " ".join(bits)

    if entity_type == "vendor_payment":
        bits = [f"Paid vendor {amount or ''}".strip()]
        if d.get("vendor_name"):
            bits.append(d["vendor_name"])
        if d.get("po_no"):
            bits.append(f"· PO {d['po_no']}")
        return " ".join(bits)

    if entity_type in ("agent", "contractor") and action in ("payment", "bonus"):
        who = d.get("name") or et
        label = "Bonus" if action == "bonus" else "Payment"
        bits = [f"{label} to {who}"]
        if amount:
            bits.append(amount)
        if d.get("reason"):
            bits.append(f"· {d['reason']}")
        return " ".join(bits)

    if entity_type in ("investor", "partner") and action in ("contribution", "distribution"):
        verb = "Contribution from" if action == "contribution" else "Distribution to"
        return f"{verb} {d.get('name') or et}" + (f" · {amount}" if amount else "")

    if entity_type == "inventory_item" and action == "movement":
        direction = (d.get("direction") or "moved").replace("out", "issued").replace("in", "received")
        qty = d.get("quantity")
        item = d.get("name") or "material"
        if qty is not None:
            return f"Stock {direction}: {qty} {d.get('unit') or 'units'} of {item}"
        return f"Stock moved · {item}"

    if entity_type == "project_stage":
        return f"{act} stage “{name or f'#{entity_id}'}”" + (f" on {project}" if project else "")

    if entity_type == "project_task":
        if action == "rescheduled":
            return (f"Rescheduled task “{name or f'#{entity_id}'}”"
                    f" to {d.get('planned_start')} → {d.get('planned_end')}")
        if action == "progress":
            return f"Task “{name or f'#{entity_id}'}” progress set to {d.get('progress_pct', '?')}%"
        return f"{act} task “{name or f'#{entity_id}'}”" + (f" · {project}" if project else "")

    if entity_type == "boq_line":
        qty = d.get("qty")
        return (f"{act} BOQ “{name or f'#{entity_id}'}”"
                + (f" · {qty} {d.get('unit') or ''}".rstrip() if qty is not None else "")
                + (f" · {amount}" if amount else ""))

    if entity_type == "project" and action == "progress":
        return f"Project progress set to {d.get('progress_pct', d.get('progress', '?'))}%" + (
            f" ({d.get('source')} mode)" if d.get("source") else "")

    if entity_type == "project" and action == "created":
        return f"Created project “{name or f'#{entity_id}'}”"

    if name and action in ("created", "create", "deleted", "removed"):
        return f"{act} {et.lower()} “{name}”" + (f" · {project}" if project else "")

    if amount:
        return f"{act} {et.lower()} · {amount}" + (f" · {name}" if name else "")

    if name:
        return f"{act} {et.lower()} “{name}”"
    if entity_id is not None:
        return f"{act} {et.lower()} #{entity_id}"
    return f"{act} {et.lower()}"


def facts(details: dict) -> list[dict]:
    """Key/value chips for the expandable facts pane — skip ids already shown elsewhere."""
    skip = {
        "project_id", "unit_id", "booking_id", "customer_id", "vendor_id", "agent_id",
        "from_customer_id", "to_customer_id", "installment_id", "purchase_order_id",
        "movement_id", "assignment_id", "checklist_id", "payment_id", "stage_id", "task_id",
        "category_id", "item_id", "template_id",
    }
    labels = {
        "booking_no": "Booking no.",
        "receipt_no": "Receipt",
        "po_no": "PO no.",
        "unit_no": "Unit",
        "customer_name": "Customer",
        "from_customer": "From",
        "to_customer": "To",
        "vendor_name": "Vendor",
        "project_name": "Project",
        "sale_price": "Sale price",
        "amount": "Amount",
        "token_amount": "Token",
        "token_applied": "Token applied",
        "transfer_fee": "Transfer fee",
        "forfeit": "Forfeit",
        "refund": "Refund",
        "fee": "Fee",
        "fee_pct": "Fee %",
        "reason": "Reason",
        "status": "Status",
        "progress_pct": "Progress",
        "planned_start": "Start",
        "planned_end": "End",
        "direction": "Direction",
        "quantity": "Qty",
        "qty": "Qty",
        "unit": "UoM",
        "name": "Name",
        "possession_date": "Possession date",
        "source": "Source",
        "note": "Note",
        "notes": "Notes",
        "payment_method": "Method",
    }
    out = []
    for key, val in (details or {}).items():
        if key in skip or val in (None, "", [], {}):
            continue
        label = labels.get(key, key.replace("_", " ").title())
        if key in _AMOUNT_KEYS or key.endswith("_amount") or key in ("forfeit", "refund", "fee", "sale_price"):
            display = _money(val) or str(val)
        elif key in ("fee_pct", "progress_pct"):
            display = f"{val}%"
        else:
            display = str(val)
        out.append({"key": key, "label": label, "value": display})
    return out


def _actor_map(user_ids: list) -> dict[int, dict]:
    ids = sorted({int(i) for i in user_ids if i})
    if not ids:
        return {}
    with platform_db() as pconn:
        rows = fetch_all(
            pconn,
            f"SELECT id, name, email, role FROM users WHERE id IN ({','.join('?' * len(ids))})",
            tuple(ids),
        )
    return {r["id"]: r for r in rows}


def _project_name(conn, project_id) -> str | None:
    if not project_id:
        return None
    row = fetch_one(conn, "SELECT name FROM projects WHERE id=?", (project_id,))
    return row["name"] if row else None


def _enrich_details(conn, entity_type: str, entity_id, details: dict) -> dict:
    """Fill in human names when the write only stored ids — safe for old rows."""
    d = dict(details or {})
    if not d.get("project_name") and d.get("project_id"):
        d["project_name"] = _project_name(conn, d["project_id"])

    if entity_type == "booking" and entity_id and not d.get("customer_name"):
        row = fetch_one(
            conn,
            """SELECT b.booking_no, b.final_sale_price AS sale_price, c.name AS customer_name,
                      u.unit_no, p.name AS project_name, p.id AS project_id
               FROM bookings b
               JOIN customers c ON c.id=b.customer_id
               JOIN units u ON u.id=b.unit_id
               JOIN projects p ON p.id=b.project_id
               WHERE b.id=?""",
            (entity_id,),
        )
        if row:
            d.setdefault("booking_no", row["booking_no"])
            d.setdefault("customer_name", row["customer_name"])
            d.setdefault("unit_no", row["unit_no"])
            d.setdefault("project_name", row["project_name"])
            d.setdefault("project_id", row["project_id"])
            d.setdefault("sale_price", row["sale_price"])

    if entity_type == "payment" and entity_id and not d.get("customer_name"):
        row = fetch_one(
            conn,
            """SELECT p.amount, r.receipt_no, c.name AS customer_name, u.unit_no,
                      pr.name AS project_name, pr.id AS project_id, p.payment_method
               FROM payments p
               JOIN bookings b ON b.id=p.booking_id
               JOIN customers c ON c.id=b.customer_id
               JOIN units u ON u.id=b.unit_id
               JOIN projects pr ON pr.id=b.project_id
               LEFT JOIN receipts r ON r.payment_id=p.id
               WHERE p.id=?""",
            (entity_id,),
        )
        if row:
            d.setdefault("amount", row["amount"])
            d.setdefault("receipt_no", row["receipt_no"])
            d.setdefault("customer_name", row["customer_name"])
            d.setdefault("unit_no", row["unit_no"])
            d.setdefault("project_name", row["project_name"])
            d.setdefault("project_id", row["project_id"])
            d.setdefault("payment_method", row["payment_method"])

    if entity_type == "unit" and entity_id and not d.get("unit_no"):
        row = fetch_one(
            conn,
            """SELECT u.unit_no, p.name AS project_name, p.id AS project_id
               FROM units u JOIN projects p ON p.id=u.project_id WHERE u.id=?""",
            (entity_id,),
        )
        if row:
            d.setdefault("unit_no", row["unit_no"])
            d.setdefault("project_name", row["project_name"])
            d.setdefault("project_id", row["project_id"])

    if entity_type == "unit_hold" and entity_id and not d.get("unit_no"):
        row = fetch_one(
            conn,
            """SELECT h.unit_id, u.unit_no, c.name AS customer_name, p.name AS project_name, p.id AS project_id
               FROM unit_holds h
               JOIN units u ON u.id=h.unit_id
               LEFT JOIN customers c ON c.id=h.customer_id
               JOIN projects p ON p.id=u.project_id
               WHERE h.id=?""",
            (entity_id,),
        )
        if row:
            d.setdefault("unit_no", row["unit_no"])
            d.setdefault("customer_name", row["customer_name"])
            d.setdefault("project_name", row["project_name"])
            d.setdefault("project_id", row["project_id"])

    if entity_type in ("project_stage", "project_task", "boq_line") and entity_id and not d.get("project_name"):
        table = {
            "project_stage": "project_stages",
            "project_task": "project_tasks",
            "boq_line": "project_boq_lines",
        }[entity_type]
        row = fetch_one(conn, f"SELECT project_id, name FROM {table} WHERE id=?", (entity_id,))
        if row:
            d.setdefault("name", row["name"])
            d.setdefault("project_id", row["project_id"])
            d.setdefault("project_name", _project_name(conn, row["project_id"]))
        elif d.get("project_id"):
            d.setdefault("project_name", _project_name(conn, d["project_id"]))

    if entity_type == "vendor_payment" and not d.get("vendor_name") and d.get("vendor_id"):
        v = fetch_one(conn, "SELECT name FROM vendors WHERE id=?", (d["vendor_id"],))
        if v:
            d["vendor_name"] = v["name"]
        if d.get("purchase_order_id") and not d.get("po_no"):
            po = fetch_one(
                conn, "SELECT po_no, project_id FROM purchase_orders WHERE id=?",
                (d["purchase_order_id"],),
            )
            if po:
                d["po_no"] = po["po_no"]
                d.setdefault("project_id", po["project_id"])
                d.setdefault("project_name", _project_name(conn, po["project_id"]))

    if entity_type in ("agent", "contractor", "investor", "partner") and entity_id and not d.get("name"):
        table = {
            "agent": "agents", "contractor": "contractors",
            "investor": "investors", "partner": "partners",
        }.get(entity_type)
        if table:
            row = fetch_one(conn, f"SELECT name FROM {table} WHERE id=?", (entity_id,))
            if row:
                d["name"] = row["name"]

    if d.get("from_customer_id") and not d.get("from_customer"):
        c = fetch_one(conn, "SELECT name FROM customers WHERE id=?", (d["from_customer_id"],))
        if c:
            d["from_customer"] = c["name"]
    if d.get("to_customer_id") and not d.get("to_customer"):
        c = fetch_one(conn, "SELECT name FROM customers WHERE id=?", (d["to_customer_id"],))
        if c:
            d["to_customer"] = c["name"]

    return d


def list_activity(
    conn,
    *,
    limit: int = 200,
    q: str | None = None,
    entity_type: str | None = None,
    module: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    project_id: int | None = None,
) -> dict:
    where = ["1=1"]
    params: list = []
    if entity_type:
        where.append("entity_type=?")
        params.append(entity_type)
    if date_from:
        where.append("created_at >= ?")
        params.append(date_from[:10])
    if date_to:
        where.append("created_at <= ?")
        params.append(date_to[:10] + " 23:59:59")

    rows = fetch_all(
        conn,
        f"""SELECT id, entity_type, entity_id, action, details, user_id, ip, created_at
            FROM audit_log WHERE {' AND '.join(where)}
            ORDER BY id DESC LIMIT ?""",
        (*params, min(max(limit, 1), 500)),
    )

    actors = _actor_map([r.get("user_id") for r in rows])
    modules = sorted(set(MODULE_BY_ENTITY.values()) | {"Other"})
    all_entities = [r["entity_type"] for r in fetch_all(
        conn, "SELECT DISTINCT entity_type FROM audit_log ORDER BY 1")]

    out = []
    needle = (q or "").strip().lower()
    for r in rows:
        details = _enrich_details(conn, r["entity_type"], r["entity_id"], parse_details(r.get("details")))
        actor = actors.get(r.get("user_id"))
        amount = _pick_amount(details)
        pid = details.get("project_id")
        pname = details.get("project_name")
        if project_id and int(pid or 0) != int(project_id):
            continue
        if module and module_for(r["entity_type"]) != module:
            continue

        summary = summarize(r["entity_type"], r["action"], details, r["entity_id"])
        fact_list = facts(details)
        actor_name = (actor or {}).get("name") or ("System" if not r.get("user_id") else f"User #{r['user_id']}")
        actor_role = (actor or {}).get("role")
        ref = _ref(details, r["entity_type"], r["entity_id"])

        if needle:
            hay = " ".join([
                summary, actor_name, ref or "", pname or "", r["entity_type"], r["action"],
                " ".join(f["value"] for f in fact_list),
            ]).lower()
            if needle not in hay:
                continue

        out.append({
            "id": r["id"],
            "when": r["created_at"],
            "created_at": r["created_at"],
            "entity_type": r["entity_type"],
            "entity_label": entity_label(r["entity_type"]),
            "entity_id": r["entity_id"],
            "action": r["action"],
            "action_label": action_label(r["action"]),
            "module": module_for(r["entity_type"]),
            "summary": summary,
            "ref": ref,
            "amount": amount,
            "project_id": pid,
            "project_name": pname,
            "actor_id": r.get("user_id"),
            "actor_name": actor_name,
            "actor_role": actor_role,
            "ip": r.get("ip"),
            "facts": fact_list,
            "details": details,
        })

    return {
        "rows": out,
        "count": len(out),
        "entities": all_entities,
        "modules": modules,
    }
