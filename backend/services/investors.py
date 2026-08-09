from datetime import date

from backend.database import fetch_all, fetch_one
from backend.services import audit as audit_svc


def _clean(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def list_investors(conn) -> list[dict]:
    investors = fetch_all(conn, "SELECT * FROM investors ORDER BY name")
    return [_enrich(conn, inv) for inv in investors]


def get_investor(conn, investor_id: int) -> dict | None:
    inv = fetch_one(conn, "SELECT * FROM investors WHERE id=?", (investor_id,))
    if not inv:
        return None
    inv = _enrich(conn, inv)
    inv["contributions"] = fetch_all(
        conn,
        """SELECT ic.* FROM investor_contributions ic
           JOIN investor_agreements a ON a.id=ic.agreement_id
           WHERE a.investor_id=? ORDER BY ic.contribution_date DESC, ic.id DESC""",
        (investor_id,),
    )
    inv["distributions"] = fetch_all(
        conn,
        """SELECT d.* FROM investor_distributions d
           JOIN investor_agreements a ON a.id=d.agreement_id
           WHERE a.investor_id=? ORDER BY d.distribution_date DESC, d.id DESC""",
        (investor_id,),
    )
    return inv


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
        ag["total_contributed"] = contrib["v"] if contrib else 0
        ag["total_distributed"] = dist["v"] if dist else 0
        total_invested += ag["total_contributed"]
        total_return += ag["total_distributed"]
    inv["agreements"] = agreements
    inv["investment_amount"] = total_invested
    inv["total_return_received"] = total_return
    inv["outstanding_return"] = max(total_invested - total_return, 0)
    first = agreements[0] if agreements else {}
    inv["investor_type"] = first.get("investor_type")
    inv["project_id"] = first.get("project_id")
    inv["agreed_amount"] = first.get("investment_amount") or 0
    inv["investment_date"] = first.get("investment_date")
    inv["monthly_return_pct"] = first.get("monthly_return_pct")
    inv["profit_share_pct"] = first.get("profit_share_pct")
    if first.get("project_id"):
        proj = fetch_one(conn, "SELECT name FROM projects WHERE id=?", (first["project_id"],))
        inv["project_name"] = proj["name"] if proj else None
    else:
        inv["project_name"] = None
    return inv


def _person_status(raw) -> str:
    status = (_clean(raw) or "active").lower().replace(" ", "_")
    if status == "inactive":
        return "withdrawn"
    if status not in ("active", "completed", "withdrawn"):
        return "active"
    return status


def _ensure_agreement(conn, investor_id: int) -> int:
    ag = fetch_one(
        conn,
        "SELECT id FROM investor_agreements WHERE investor_id=? ORDER BY id LIMIT 1",
        (investor_id,),
    )
    if ag:
        return ag["id"]
    cur = conn.execute(
        """INSERT INTO investor_agreements(investor_id, project_id, investor_type,
           investment_amount, investment_date, status)
           VALUES(?,?,?,?,?,?)""",
        (investor_id, None, "Profit Sharing", 0, date.today().isoformat(), "active"),
    )
    return cur.lastrowid


def _sync_agreement(conn, investor_id: int, data: dict) -> None:
    ag_id = _ensure_agreement(conn, investor_id)
    inv_type = _clean(data.get("investor_type")) or "Profit Sharing"
    if inv_type not in ("Monthly Return", "Profit Sharing"):
        inv_type = "Profit Sharing"
    project_id = data.get("project_id")
    if project_id in ("", None):
        project_id = None
    else:
        try:
            project_id = int(project_id)
        except (TypeError, ValueError):
            project_id = None
        if project_id and not fetch_one(conn, "SELECT id FROM projects WHERE id=?", (project_id,)):
            raise ValueError("Project not found")
    try:
        agreed = int(data.get("agreed_amount") or 0)
    except (TypeError, ValueError):
        agreed = 0
    inv_date = _clean(data.get("investment_date")) or date.today().isoformat()

    def _pct(key):
        raw = data.get(key)
        if raw in (None, ""):
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    monthly = _pct("monthly_return_pct")
    profit = _pct("profit_share_pct")
    ag_status = _person_status(data.get("status"))
    conn.execute(
        """UPDATE investor_agreements SET project_id=?, investor_type=?, investment_amount=?,
           investment_date=?, monthly_return_pct=?, profit_share_pct=?, status=?
           WHERE id=?""",
        (project_id, inv_type, agreed, inv_date, monthly, profit, ag_status, ag_id),
    )


def create_investor(conn, data: dict) -> dict:
    name = _clean(data.get("name"))
    if not name:
        raise ValueError("Investor name is required")
    status = _person_status(data.get("status"))
    cur = conn.execute(
        """INSERT INTO investors(name, cnic, mobile_number, email, description, status)
           VALUES(?,?,?,?,?,?)""",
        (
            name, _clean(data.get("cnic")), _clean(data.get("mobile_number") or data.get("contact")),
            _clean(data.get("email")), _clean(data.get("description")), status,
        ),
    )
    inv_id = cur.lastrowid
    _sync_agreement(conn, inv_id, data)
    audit_svc.log(conn, "investor", inv_id, "created", {"name": name})
    return get_investor(conn, inv_id)


def update_investor(conn, investor_id: int, data: dict) -> dict | None:
    if not fetch_one(conn, "SELECT id FROM investors WHERE id=?", (investor_id,)):
        return None
    name = _clean(data.get("name"))
    if not name:
        raise ValueError("Investor name is required")
    status = _person_status(data.get("status"))
    conn.execute(
        """UPDATE investors SET name=?, cnic=?, mobile_number=?, email=?, description=?, status=?
           WHERE id=?""",
        (
            name, _clean(data.get("cnic")), _clean(data.get("mobile_number") or data.get("contact")),
            _clean(data.get("email")), _clean(data.get("description")), status, investor_id,
        ),
    )
    _sync_agreement(conn, investor_id, data)
    return get_investor(conn, investor_id)


def delete_investor(conn, investor_id: int) -> None:
    if not fetch_one(conn, "SELECT id FROM investors WHERE id=?", (investor_id,)):
        raise ValueError("Investor not found")
    money = fetch_one(
        conn,
        """SELECT
             (SELECT COUNT(*) FROM investor_contributions ic
              JOIN investor_agreements a ON a.id=ic.agreement_id WHERE a.investor_id=?)
           + (SELECT COUNT(*) FROM investor_distributions d
              JOIN investor_agreements a ON a.id=d.agreement_id WHERE a.investor_id=?) AS n""",
        (investor_id, investor_id),
    )
    if money and money["n"]:
        raise ValueError("Cannot delete an investor with money history")
    conn.execute("DELETE FROM investor_agreements WHERE investor_id=?", (investor_id,))
    conn.execute("DELETE FROM investors WHERE id=?", (investor_id,))


def add_contribution(conn, investor_id: int, data: dict) -> dict:
    if not fetch_one(conn, "SELECT id FROM investors WHERE id=?", (investor_id,)):
        raise ValueError("Investor not found")
    amount = int(data.get("amount") or 0)
    if amount <= 0:
        raise ValueError("Amount must be greater than 0")
    agreement_id = data.get("agreement_id") or _ensure_agreement(conn, investor_id)
    pay_date = _clean(data.get("contribution_date")) or date.today().isoformat()
    conn.execute(
        """INSERT INTO investor_contributions(agreement_id, amount, contribution_date, notes)
           VALUES(?,?,?,?)""",
        (agreement_id, amount, pay_date, _clean(data.get("notes"))),
    )
    audit_svc.log(conn, "investor", investor_id, "contribution", {"amount": amount})
    return get_investor(conn, investor_id)


def add_distribution(conn, investor_id: int, data: dict) -> dict:
    if not fetch_one(conn, "SELECT id FROM investors WHERE id=?", (investor_id,)):
        raise ValueError("Investor not found")
    amount = int(data.get("amount") or 0)
    if amount <= 0:
        raise ValueError("Amount must be greater than 0")
    agreement_id = data.get("agreement_id") or _ensure_agreement(conn, investor_id)
    pay_date = _clean(data.get("distribution_date")) or date.today().isoformat()
    conn.execute(
        """INSERT INTO investor_distributions(agreement_id, amount, distribution_date, notes)
           VALUES(?,?,?,?)""",
        (agreement_id, amount, pay_date, _clean(data.get("notes"))),
    )
    audit_svc.log(conn, "investor", investor_id, "distribution", {"amount": amount})
    return get_investor(conn, investor_id)
