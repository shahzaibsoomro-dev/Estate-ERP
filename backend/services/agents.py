from datetime import date

from backend.database import fetch_all, fetch_one
from backend.services import audit as audit_svc

COMMISSION_MODES = ("percent", "flat", "over_base")


def _clean(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_commission_mode(raw) -> str:
    text = (_clean(raw) or "percent").lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "percentage": "percent",
        "pct": "percent",
        "rate": "percent",
        "amount": "flat",
        "pkr": "flat",
        "fixed": "flat",
        "fixed_pkr": "flat",
        "fixed_amount": "flat",
        "surplus": "over_base",
        "above_base": "over_base",
        "overbase": "over_base",
        "over_base_price": "over_base",
        "milestone": "over_base",
    }
    text = aliases.get(text, text)
    return text if text in COMMISSION_MODES else "percent"


def _pct(raw, default: float | None = None) -> float | None:
    if raw in (None, ""):
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return value


def compute_booking_commission(
    mode,
    sale_price: int,
    base_price: int | None = None,
    rate_pct: float | None = None,
    flat_amount: int | None = None,
    over_base_pct: float | None = None,
) -> dict:
    """Resolve commission for a sale. over_base = anything above the unit's base price."""
    mode = normalize_commission_mode(mode)
    sale = int(sale_price or 0)
    base = int(base_price or 0)
    surplus = max(sale - base, 0)
    rate = _pct(rate_pct, 0.0) or 0.0
    share = _pct(over_base_pct, 100.0)
    if share is None:
        share = 100.0
    try:
        flat = int(flat_amount or 0)
    except (TypeError, ValueError):
        flat = 0
    if flat < 0:
        flat = 0

    if mode == "flat":
        amount = flat
        stored_rate = 0.0
    elif mode == "over_base":
        if share < 0 or share > 100:
            raise ValueError("Over-base share must be between 0 and 100")
        amount = int(round(surplus * share / 100.0))
        stored_rate = share
        flat = 0
    else:
        if rate < 0 or rate > 100:
            raise ValueError("Commission rate must be between 0 and 100")
        amount = int(round(sale * rate / 100.0))
        stored_rate = rate
        flat = 0
        share = None

    return {
        "mode": mode,
        "rate_pct": stored_rate,
        "flat_amount": flat,
        "base_price": base,
        "sale_price": sale,
        "surplus": surplus,
        "over_base_pct": share if mode == "over_base" else None,
        "commission_amount": max(amount, 0),
    }


def commission_label(ag: dict) -> str:
    mode = normalize_commission_mode(ag.get("commission_mode"))
    if mode == "flat":
        amt = int(ag.get("default_flat_amount") or 0)
        return f"PKR {amt:,} fixed"
    if mode == "over_base":
        share = ag.get("over_base_pct")
        share = 100 if share in (None, "") else share
        return f"Above base ({share:g}% of surplus)"
    rate = ag.get("default_rate_pct") if ag.get("default_rate_pct") is not None else ag.get("rate")
    rate = 0 if rate in (None, "") else rate
    return f"{rate:g}% of sale"


def normalize_agent(data: dict) -> dict:
    name = _clean(data.get("name"))
    if not name:
        raise ValueError("Agent name is required")
    status = (_clean(data.get("status")) or "active").lower()
    if status not in ("active", "inactive"):
        status = "active"
    mode = normalize_commission_mode(data.get("commission_mode"))
    rate = _pct(data.get("default_rate_pct"), 2.0 if mode == "percent" else 0.0)
    if rate is None:
        rate = 2.0 if mode == "percent" else 0.0
    if rate < 0 or rate > 100:
        raise ValueError("Commission rate must be between 0 and 100")
    try:
        flat = int(data.get("default_flat_amount") or 0)
    except (TypeError, ValueError):
        flat = 0
    if flat < 0:
        raise ValueError("Fixed commission cannot be negative")
    share = _pct(data.get("over_base_pct"), None)
    if share is None and mode == "over_base":
        share = _pct(data.get("default_rate_pct"), 100.0)
    if share is None:
        share = 100.0
    if share < 0 or share > 100:
        raise ValueError("Over-base share must be between 0 and 100")
    if mode != "percent":
        rate = rate if mode == "over_base" else 0.0
    if mode != "flat":
        flat = 0
    if mode != "over_base":
        share = 100.0
    try:
        bonus_budget = int(data.get("bonus_budget") or 0)
    except (TypeError, ValueError):
        bonus_budget = 0
    if bonus_budget < 0:
        raise ValueError("Bonus budget cannot be negative")
    return {
        "name": name,
        "description": _clean(data.get("description")),
        "contact": _clean(data.get("contact")),
        "category": _clean(data.get("category")),
        "commission_mode": mode,
        "default_rate_pct": rate if mode == "percent" else (share if mode == "over_base" else 0.0),
        "default_flat_amount": flat,
        "over_base_pct": share,
        "bonus_budget": bonus_budget,
        "status": status,
    }


def _comm_totals(conn, agent_id: int) -> dict:
    row = fetch_one(
        conn,
        """SELECT COALESCE(SUM(commission_amount),0) AS earned,
                  COALESCE(SUM(paid_amount),0) AS paid,
                  COUNT(*) AS bookings_count
           FROM agent_commissions
           WHERE agent_id=? AND status!='reversed'""",
        (agent_id,),
    )
    return row or {"earned": 0, "paid": 0, "bookings_count": 0}


def _bonus_totals(conn, agent_id: int) -> dict:
    row = fetch_one(
        conn,
        "SELECT COALESCE(SUM(amount),0) AS paid FROM agent_bonuses WHERE agent_id=?",
        (agent_id,),
    )
    return {"bonus_paid": (row["paid"] if row else 0)}


def _attach_summary(conn, ag: dict) -> dict:
    comm = _comm_totals(conn, ag["id"])
    bonus = _bonus_totals(conn, ag["id"])
    budget = int(ag.get("bonus_budget") or 0)
    paid_bonus = int(bonus["bonus_paid"] or 0)
    ag["commission_earned"] = comm["earned"]
    ag["commission_paid"] = comm["paid"]
    ag["commission_unpaid"] = max((comm["earned"] or 0) - (comm["paid"] or 0), 0)
    ag["bookings_count"] = comm["bookings_count"]
    ag["commission_mode"] = normalize_commission_mode(ag.get("commission_mode"))
    ag["default_flat_amount"] = int(ag.get("default_flat_amount") or 0)
    if ag.get("over_base_pct") is None:
        ag["over_base_pct"] = 100.0
    ag["rate"] = ag.get("default_rate_pct")
    ag["commission_label"] = commission_label(ag)
    ag["bonus_budget"] = budget
    ag["bonus_paid"] = paid_bonus
    ag["bonus_remaining"] = max(budget - paid_bonus, 0)
    ag["master_id"] = f"AGT-{ag['id']}"
    proj = fetch_one(
        conn,
        """SELECT p.name FROM bookings b
           JOIN projects p ON p.id=b.project_id
           WHERE b.agent_id=? AND b.status='active'
           ORDER BY b.id DESC LIMIT 1""",
        (ag["id"],),
    )
    ag["project"] = proj["name"] if proj else "—"
    return ag


def list_agents(conn, active_only: bool = False) -> list[dict]:
    q = "SELECT * FROM agents"
    if active_only:
        q += " WHERE status='active'"
    q += " ORDER BY name"
    agents = fetch_all(conn, q)
    for ag in agents:
        _attach_summary(conn, ag)
    return agents


def get_agent(conn, agent_id: int) -> dict | None:
    ag = fetch_one(conn, "SELECT * FROM agents WHERE id=?", (agent_id,))
    if not ag:
        return None
    _attach_summary(conn, ag)
    ag["commissions"] = fetch_all(
        conn,
        """SELECT ac.*, b.booking_no, b.final_sale_price,
                  u.unit_no, u.base_sale_price AS unit_base_price,
                  p.name AS project_name, c.name AS customer_name,
                  (ac.commission_amount - ac.paid_amount) AS remaining
           FROM agent_commissions ac
           JOIN bookings b ON b.id=ac.booking_id
           JOIN units u ON u.id=b.unit_id
           JOIN projects p ON p.id=b.project_id
           JOIN customers c ON c.id=b.customer_id
           WHERE ac.agent_id=?
           ORDER BY ac.id DESC""",
        (agent_id,),
    )
    ag["payments"] = fetch_all(
        conn,
        """SELECT acp.*, b.booking_no
           FROM agent_commission_payments acp
           JOIN agent_commissions ac ON ac.id=acp.commission_id
           JOIN bookings b ON b.id=ac.booking_id
           WHERE ac.agent_id=?
           ORDER BY acp.payment_date DESC, acp.id DESC""",
        (agent_id,),
    )
    ag["bonuses"] = fetch_all(
        conn,
        """SELECT * FROM agent_bonuses WHERE agent_id=?
           ORDER BY bonus_date DESC, id DESC""",
        (agent_id,),
    )
    return ag


def create_agent(conn, data: dict) -> dict:
    payload = normalize_agent(data)
    cur = conn.execute(
        """INSERT INTO agents(name, description, contact, category, commission_mode,
           default_rate_pct, default_flat_amount, over_base_pct, bonus_budget, status)
           VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (
            payload["name"], payload["description"], payload["contact"], payload["category"],
            payload["commission_mode"], payload["default_rate_pct"], payload["default_flat_amount"],
            payload["over_base_pct"], payload["bonus_budget"], payload["status"],
        ),
    )
    return get_agent(conn, cur.lastrowid)


def update_agent(conn, agent_id: int, data: dict) -> dict | None:
    if not fetch_one(conn, "SELECT id FROM agents WHERE id=?", (agent_id,)):
        return None
    payload = normalize_agent(data)
    conn.execute(
        """UPDATE agents SET name=?, description=?, contact=?, category=?, commission_mode=?,
           default_rate_pct=?, default_flat_amount=?, over_base_pct=?,
           bonus_budget=?, status=?
           WHERE id=?""",
        (
            payload["name"], payload["description"], payload["contact"], payload["category"],
            payload["commission_mode"], payload["default_rate_pct"], payload["default_flat_amount"],
            payload["over_base_pct"], payload["bonus_budget"], payload["status"], agent_id,
        ),
    )
    return get_agent(conn, agent_id)


def delete_agent(conn, agent_id: int) -> None:
    if not fetch_one(conn, "SELECT id FROM agents WHERE id=?", (agent_id,)):
        raise ValueError("Agent not found")
    if fetch_one(conn, "SELECT id FROM agent_commissions WHERE agent_id=? LIMIT 1", (agent_id,)):
        raise ValueError("Cannot delete an agent with commission history")
    if fetch_one(conn, "SELECT id FROM agent_bonuses WHERE agent_id=? LIMIT 1", (agent_id,)):
        raise ValueError("Cannot delete an agent with bonus history")
    if fetch_one(conn, "SELECT id FROM bookings WHERE agent_id=? LIMIT 1", (agent_id,)):
        raise ValueError("Cannot delete an agent linked to bookings")
    conn.execute("DELETE FROM agents WHERE id=?", (agent_id,))


def pay_commission(
    conn, agent_id: int, amount: int, payment_date: str | None,
    notes: str | None = None, commission_id: int | None = None,
) -> dict:
    if not fetch_one(conn, "SELECT id FROM agents WHERE id=?", (agent_id,)):
        raise ValueError("Agent not found")
    amount = int(amount or 0)
    if amount <= 0:
        raise ValueError("Amount must be greater than 0")
    pay_date = _clean(payment_date) or date.today().isoformat()
    q = """SELECT * FROM agent_commissions
           WHERE agent_id=? AND status!='reversed' AND paid_amount < commission_amount"""
    params: list = [agent_id]
    if commission_id:
        q += " AND id=?"
        params.append(commission_id)
    q += " ORDER BY id"
    unpaid = fetch_all(conn, q, tuple(params))
    if not unpaid:
        raise ValueError("Nothing outstanding for this agent")
    due_total = sum(c["commission_amount"] - c["paid_amount"] for c in unpaid)
    if amount > due_total:
        raise ValueError("Payment exceeds unpaid commission")
    remaining = amount
    for c in unpaid:
        if remaining <= 0:
            break
        due = c["commission_amount"] - c["paid_amount"]
        pay = min(remaining, due)
        conn.execute(
            "INSERT INTO agent_commission_payments(commission_id, amount, payment_date, notes) VALUES(?,?,?,?)",
            (c["id"], pay, pay_date, _clean(notes)),
        )
        new_paid = c["paid_amount"] + pay
        status = "paid" if new_paid >= c["commission_amount"] else "partial"
        conn.execute(
            "UPDATE agent_commissions SET paid_amount=?, status=? WHERE id=?",
            (new_paid, status, c["id"]),
        )
        remaining -= pay
    audit_svc.log(conn, "agent", agent_id, "payment", {"amount": amount})
    return get_agent(conn, agent_id)


def award_bonus(
    conn, agent_id: int, amount: int, bonus_date: str | None = None,
    reason: str | None = None, notes: str | None = None,
) -> dict:
    ag = get_agent(conn, agent_id)
    if not ag:
        raise ValueError("Agent not found")
    amount = int(amount or 0)
    if amount <= 0:
        raise ValueError("Bonus amount must be greater than 0")
    remaining = int(ag.get("bonus_remaining") or 0)
    if amount > remaining:
        raise ValueError(
            f"Bonus exceeds remaining budget ({remaining} of {ag.get('bonus_budget') or 0})"
        )
    pay_date = _clean(bonus_date) or date.today().isoformat()
    conn.execute(
        """INSERT INTO agent_bonuses(agent_id, amount, bonus_date, reason, notes)
           VALUES(?,?,?,?,?)""",
        (agent_id, amount, pay_date, _clean(reason), _clean(notes)),
    )
    audit_svc.log(conn, "agent", agent_id, "bonus", {"amount": amount, "reason": reason})
    return get_agent(conn, agent_id)
