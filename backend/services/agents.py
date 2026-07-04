from backend.database import fetch_all, fetch_one


def list_agents(conn) -> list[dict]:
    agents = fetch_all(conn, "SELECT * FROM agents ORDER BY name")
    for ag in agents:
        comm = fetch_one(
            conn,
            """SELECT COALESCE(SUM(commission_amount),0) AS earned,
                      COALESCE(SUM(paid_amount),0) AS paid,
                      COUNT(*) AS bookings_count
               FROM agent_commissions WHERE agent_id=?""",
            (ag["id"],),
        )
        ag["commission_earned"] = comm["earned"] if comm else 0
        ag["commission_paid"] = comm["paid"] if comm else 0
        ag["bookings_count"] = comm["bookings_count"] if comm else 0
        ag["rate"] = ag.get("default_rate_pct")
        proj = fetch_one(
            conn,
            """SELECT p.name FROM bookings b
               JOIN projects p ON p.id=b.project_id
               WHERE b.agent_id=? LIMIT 1""",
            (ag["id"],),
        )
        ag["project"] = proj["name"] if proj else "—"
    return agents


def get_agent(conn, agent_id: int) -> dict | None:
    ag = fetch_one(conn, "SELECT * FROM agents WHERE id=?", (agent_id,))
    if not ag:
        return None
    return _enrich_one(conn, ag)


def _enrich_one(conn, ag: dict) -> dict:
    comm = fetch_one(
        conn,
        """SELECT COALESCE(SUM(commission_amount),0) AS earned,
                  COALESCE(SUM(paid_amount),0) AS paid,
                  COUNT(*) AS bookings_count
           FROM agent_commissions WHERE agent_id=?""",
        (ag["id"],),
    )
    ag["commission_earned"] = comm["earned"] if comm else 0
    ag["commission_paid"] = comm["paid"] if comm else 0
    ag["bookings_count"] = comm["bookings_count"] if comm else 0
    ag["rate"] = ag.get("default_rate_pct")
    ag["commissions"] = fetch_all(
        conn,
        """SELECT ac.*, b.booking_no, b.final_sale_price FROM agent_commissions ac
           JOIN bookings b ON b.id=ac.booking_id WHERE ac.agent_id=?""",
        (ag["id"],),
    )
    return ag


def create_agent(conn, data: dict) -> dict:
    cur = conn.execute(
        """INSERT INTO agents(name, description, contact, default_rate_pct, status)
           VALUES(?,?,?,?,?)""",
        (
            data["name"], data.get("description"), data.get("contact"),
            data.get("default_rate_pct", 2.0), data.get("status", "active"),
        ),
    )
    ag = fetch_one(conn, "SELECT * FROM agents WHERE id=?", (cur.lastrowid,))
    return _enrich_one(conn, ag)


def pay_commission(conn, agent_id: int, amount: int, payment_date: str, notes: str | None = None) -> dict:
    unpaid = fetch_all(
        conn,
        """SELECT * FROM agent_commissions
           WHERE agent_id=? AND paid_amount < commission_amount ORDER BY id""",
        (agent_id,),
    )
    remaining = amount
    for c in unpaid:
        if remaining <= 0:
            break
        due = c["commission_amount"] - c["paid_amount"]
        pay = min(remaining, due)
        conn.execute(
            "INSERT INTO agent_commission_payments(commission_id, amount, payment_date, notes) VALUES(?,?,?,?)",
            (c["id"], pay, payment_date, notes),
        )
        new_paid = c["paid_amount"] + pay
        status = "paid" if new_paid >= c["commission_amount"] else "partial"
        conn.execute(
            "UPDATE agent_commissions SET paid_amount=?, status=? WHERE id=?",
            (new_paid, status, c["id"]),
        )
        remaining -= pay
    ag = fetch_one(conn, "SELECT * FROM agents WHERE id=?", (agent_id,))
    return _enrich_one(conn, ag)
