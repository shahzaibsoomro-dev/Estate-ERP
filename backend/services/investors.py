from backend.database import fetch_all, fetch_one


def list_investors(conn) -> list[dict]:
    investors = fetch_all(conn, "SELECT * FROM investors ORDER BY name")
    return [_enrich(conn, inv) for inv in investors]


def _enrich(conn, inv: dict) -> dict:
    agreements = fetch_all(
        conn, "SELECT * FROM investor_agreements WHERE investor_id=?", (inv["id"],),
    )
    total_invested = 0
    total_return = 0
    for ag in agreements:
        contrib = fetch_one(
            conn,
            "SELECT COALESCE(SUM(amount),0) AS v FROM investor_contributions WHERE agreement_id=?",
            (ag["id"],),
        )
        dist = fetch_one(
            conn,
            "SELECT COALESCE(SUM(amount),0) AS v FROM investor_distributions WHERE agreement_id=?",
            (ag["id"],),
        )
        ag["total_contributed"] = contrib["v"] if contrib else ag["investment_amount"]
        ag["total_distributed"] = dist["v"] if dist else 0
        total_invested += ag["total_contributed"]
        total_return += ag["total_distributed"]
    inv["agreements"] = agreements
    inv["investment_amount"] = total_invested
    inv["total_return_received"] = total_return
    inv["outstanding_return"] = max(total_invested - total_return, 0)
    return inv


def create_investor(conn, data: dict) -> dict:
    cur = conn.execute(
        """INSERT INTO investors(name, cnic, mobile_number, email, description, status)
           VALUES(?,?,?,?,?,?)""",
        (
            data["name"], data.get("cnic"), data.get("mobile_number"),
            data.get("email"), data.get("description"), data.get("status", "active"),
        ),
    )
    inv = fetch_one(conn, "SELECT * FROM investors WHERE id=?", (cur.lastrowid,))
    if data.get("investor_type"):
        conn.execute(
            """INSERT INTO investor_agreements(investor_id, project_id, investor_type,
               investment_amount, investment_date, monthly_return_pct, profit_share_pct, status)
               VALUES(?,?,?,?,?,?,?,?)""",
            (
                inv["id"], data.get("project_id"), data["investor_type"],
                data.get("investment_amount", 0), data.get("investment_date"),
                data.get("monthly_return_pct"), data.get("profit_share_pct"),
                data.get("status", "active"),
            ),
        )
    return _enrich(conn, inv)


def add_contribution(conn, investor_id: int, data: dict) -> dict:
    agreement_id = data.get("agreement_id")
    if not agreement_id:
        ag = fetch_one(
            conn,
            "SELECT id FROM investor_agreements WHERE investor_id=? ORDER BY id LIMIT 1",
            (investor_id,),
        )
        if not ag:
            raise ValueError("No agreement found for investor")
        agreement_id = ag["id"]
    conn.execute(
        """INSERT INTO investor_contributions(agreement_id, amount, contribution_date, notes)
           VALUES(?,?,?,?)""",
        (agreement_id, data["amount"], data["contribution_date"], data.get("notes")),
    )
    inv = fetch_one(conn, "SELECT * FROM investors WHERE id=?", (investor_id,))
    return _enrich(conn, inv)


def add_distribution(conn, investor_id: int, data: dict) -> dict:
    agreement_id = data.get("agreement_id")
    if not agreement_id:
        ag = fetch_one(
            conn,
            "SELECT id FROM investor_agreements WHERE investor_id=? ORDER BY id LIMIT 1",
            (investor_id,),
        )
        if not agreement_id and not ag:
            raise ValueError("No agreement found for investor")
        agreement_id = ag["id"] if ag else agreement_id
    conn.execute(
        """INSERT INTO investor_distributions(agreement_id, amount, distribution_date, notes)
           VALUES(?,?,?,?)""",
        (agreement_id, data["amount"], data["distribution_date"], data.get("notes")),
    )
    inv = fetch_one(conn, "SELECT * FROM investors WHERE id=?", (investor_id,))
    return _enrich(conn, inv)
