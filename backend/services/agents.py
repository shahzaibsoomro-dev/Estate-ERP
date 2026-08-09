from datetime import date

from backend.database import fetch_all, fetch_one


def _clean(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_agent(data: dict) -> dict:
    name = _clean(data.get("name"))
    if not name:
        raise ValueError("Agent name is required")
    status = (_clean(data.get("status")) or "active").lower()
    if status not in ("active", "inactive"):
        status = "active"
    try:
        rate = float(data.get("default_rate_pct") if data.get("default_rate_pct") is not None else 2.0)
    except (TypeError, ValueError):
        rate = 2.0
    if rate < 0 or rate > 100:
        raise ValueError("Commission rate must be between 0 and 100")
    return {
        "name": name,
        "description": _clean(data.get("description")),
        "contact": _clean(data.get("contact")),
        "default_rate_pct": rate,
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


def _attach_summary(conn, ag: dict) -> dict:
    comm = _comm_totals(conn, ag["id"])
    ag["commission_earned"] = comm["earned"]
    ag["commission_paid"] = comm["paid"]
    ag["commission_unpaid"] = max((comm["earned"] or 0) - (comm["paid"] or 0), 0)
    ag["bookings_count"] = comm["bookings_count"]
    ag["rate"] = ag.get("default_rate_pct")
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
                  u.unit_no, p.name AS project_name, c.name AS customer_name,
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
    return ag


def create_agent(conn, data: dict) -> dict:
    payload = normalize_agent(data)
    cur = conn.execute(
        """INSERT INTO agents(name, description, contact, default_rate_pct, status)
           VALUES(?,?,?,?,?)""",
        (
            payload["name"], payload["description"], payload["contact"],
            payload["default_rate_pct"], payload["status"],
        ),
    )
    return get_agent(conn, cur.lastrowid)


def update_agent(conn, agent_id: int, data: dict) -> dict | None:
    if not fetch_one(conn, "SELECT id FROM agents WHERE id=?", (agent_id,)):
        return None
    payload = normalize_agent(data)
    conn.execute(
        """UPDATE agents SET name=?, description=?, contact=?, default_rate_pct=?, status=?
           WHERE id=?""",
        (
            payload["name"], payload["description"], payload["contact"],
            payload["default_rate_pct"], payload["status"], agent_id,
        ),
    )
    return get_agent(conn, agent_id)


def delete_agent(conn, agent_id: int) -> None:
    if not fetch_one(conn, "SELECT id FROM agents WHERE id=?", (agent_id,)):
        raise ValueError("Agent not found")
    if fetch_one(conn, "SELECT id FROM agent_commissions WHERE agent_id=? LIMIT 1", (agent_id,)):
        raise ValueError("Cannot delete an agent with commission history")
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
    return get_agent(conn, agent_id)
