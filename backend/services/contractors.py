"""Site contractors — project assignments and payments."""

from datetime import date

from backend.database import fetch_all, fetch_one
from backend.services import audit as audit_svc


def _clean(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _status(raw) -> str:
    st = (_clean(raw) or "active").lower()
    return st if st in ("active", "inactive", "completed") else "active"


def normalize(data: dict) -> dict:
    name = _clean(data.get("name"))
    if not name:
        raise ValueError("Contractor name is required")
    return {
        "name": name,
        "company_name": _clean(data.get("company_name")),
        "father_name": _clean(data.get("father_name")),
        "cnic": _clean(data.get("cnic")),
        "contact": _clean(data.get("contact")),
        "emergency_contact": _clean(data.get("emergency_contact")),
        "email": _clean(data.get("email")),
        "address": _clean(data.get("address")),
        "city": _clean(data.get("city")),
        "ntn": _clean(data.get("ntn")),
        "pec_no": _clean(data.get("pec_no")),
        "specialty": _clean(data.get("specialty")),
        "bank_name": _clean(data.get("bank_name")),
        "account_title": _clean(data.get("account_title")),
        "account_no": _clean(data.get("account_no")),
        "description": _clean(data.get("description")),
        "status": _status(data.get("status")),
    }


def _attach(conn, row: dict) -> dict:
    cid = row["id"]
    paid = fetch_one(
        conn,
        "SELECT COALESCE(SUM(amount),0) AS v FROM contractor_payments WHERE contractor_id=?",
        (cid,),
    )
    contracted = fetch_one(
        conn,
        """SELECT COALESCE(SUM(contract_amount),0) AS v FROM contractor_assignments
           WHERE contractor_id=? AND status!='cancelled'""",
        (cid,),
    )
    row["master_id"] = f"CTR-{cid}"
    row["total_contracted"] = contracted["v"] if contracted else 0
    row["total_paid"] = paid["v"] if paid else 0
    row["balance"] = max(row["total_contracted"] - row["total_paid"], 0)
    return row


def list_contractors(conn, project_ids: list[int] | None = None) -> list[dict]:
    if project_ids:
        ph = ",".join("?" * len(project_ids))
        rows = fetch_all(
            conn,
            f"""SELECT DISTINCT c.* FROM contractors c
                JOIN contractor_assignments a ON a.contractor_id=c.id
                WHERE a.project_id IN ({ph}) AND a.status!='cancelled'
                ORDER BY c.name""",
            tuple(project_ids),
        )
    else:
        rows = fetch_all(conn, "SELECT * FROM contractors ORDER BY name")
    return [_attach(conn, r) for r in rows]


def get_contractor(conn, contractor_id: int) -> dict | None:
    row = fetch_one(conn, "SELECT * FROM contractors WHERE id=?", (contractor_id,))
    if not row:
        return None
    _attach(conn, row)
    row["assignments"] = fetch_all(
        conn,
        """SELECT a.*, p.name AS project_name
           FROM contractor_assignments a
           JOIN projects p ON p.id=a.project_id
           WHERE a.contractor_id=?
           ORDER BY a.id DESC""",
        (contractor_id,),
    )
    row["payments"] = fetch_all(
        conn,
        """SELECT cp.*, p.name AS project_name
           FROM contractor_payments cp
           LEFT JOIN projects p ON p.id=cp.project_id
           WHERE cp.contractor_id=?
           ORDER BY cp.payment_date DESC, cp.id DESC""",
        (contractor_id,),
    )
    return row


def create_contractor(conn, data: dict) -> dict:
    payload = normalize(data)
    cur = conn.execute(
        """INSERT INTO contractors(
             name, company_name, father_name, cnic, contact, emergency_contact, email,
             address, city, ntn, pec_no, specialty, bank_name, account_title, account_no,
             description, status)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            payload["name"], payload["company_name"], payload["father_name"], payload["cnic"],
            payload["contact"], payload["emergency_contact"], payload["email"],
            payload["address"], payload["city"], payload["ntn"], payload["pec_no"],
            payload["specialty"], payload["bank_name"], payload["account_title"],
            payload["account_no"], payload["description"], payload["status"],
        ),
    )
    audit_svc.log(conn, "contractor", cur.lastrowid, "created", {"name": payload["name"]})
    return get_contractor(conn, cur.lastrowid)


def update_contractor(conn, contractor_id: int, data: dict) -> dict | None:
    if not fetch_one(conn, "SELECT id FROM contractors WHERE id=?", (contractor_id,)):
        return None
    payload = normalize(data)
    conn.execute(
        """UPDATE contractors SET name=?, company_name=?, father_name=?, cnic=?, contact=?,
           emergency_contact=?, email=?, address=?, city=?, ntn=?, pec_no=?, specialty=?,
           bank_name=?, account_title=?, account_no=?, description=?, status=?
           WHERE id=?""",
        (
            payload["name"], payload["company_name"], payload["father_name"], payload["cnic"],
            payload["contact"], payload["emergency_contact"], payload["email"],
            payload["address"], payload["city"], payload["ntn"], payload["pec_no"],
            payload["specialty"], payload["bank_name"], payload["account_title"],
            payload["account_no"], payload["description"], payload["status"], contractor_id,
        ),
    )
    return get_contractor(conn, contractor_id)


def delete_contractor(conn, contractor_id: int) -> None:
    if not fetch_one(conn, "SELECT id FROM contractors WHERE id=?", (contractor_id,)):
        raise ValueError("Contractor not found")
    if fetch_one(conn, "SELECT id FROM contractor_payments WHERE contractor_id=? LIMIT 1", (contractor_id,)):
        raise ValueError("Cannot delete a contractor with payment history")
    if fetch_one(conn, "SELECT id FROM contractor_assignments WHERE contractor_id=? LIMIT 1", (contractor_id,)):
        raise ValueError("Cannot delete a contractor with project assignments")
    conn.execute("DELETE FROM contractors WHERE id=?", (contractor_id,))


def assign_project(conn, contractor_id: int, data: dict) -> dict:
    if not fetch_one(conn, "SELECT id FROM contractors WHERE id=?", (contractor_id,)):
        raise ValueError("Contractor not found")
    project_id = int(data.get("project_id") or 0)
    if not project_id or not fetch_one(conn, "SELECT id FROM projects WHERE id=?", (project_id,)):
        raise ValueError("Project not found")
    try:
        amount = int(data.get("contract_amount") or 0)
    except (TypeError, ValueError):
        amount = 0
    if amount < 0:
        raise ValueError("Contract amount cannot be negative")
    cur = conn.execute(
        """INSERT INTO contractor_assignments(
             contractor_id, project_id, role, contract_amount, start_date, end_date, status, notes)
           VALUES(?,?,?,?,?,?,?,?)""",
        (
            contractor_id, project_id, _clean(data.get("role")), amount,
            _clean(data.get("start_date")), _clean(data.get("end_date")),
            _status(data.get("status")), _clean(data.get("notes")),
        ),
    )
    audit_svc.log(conn, "contractor", contractor_id, "assigned", {
        "project_id": project_id, "assignment_id": cur.lastrowid,
    })
    return get_contractor(conn, contractor_id)


def record_payment(conn, contractor_id: int, data: dict) -> dict:
    if not fetch_one(conn, "SELECT id FROM contractors WHERE id=?", (contractor_id,)):
        raise ValueError("Contractor not found")
    amount = int(data.get("amount") or 0)
    if amount <= 0:
        raise ValueError("Amount must be greater than 0")
    project_id = data.get("project_id")
    if project_id in ("", None):
        project_id = None
    else:
        project_id = int(project_id)
    assignment_id = data.get("assignment_id")
    if assignment_id in ("", None):
        assignment_id = None
    else:
        assignment_id = int(assignment_id)
    pay_date = _clean(data.get("payment_date")) or date.today().isoformat()
    conn.execute(
        """INSERT INTO contractor_payments(
             contractor_id, assignment_id, project_id, amount, payment_date,
             payment_method, reference_number, notes)
           VALUES(?,?,?,?,?,?,?,?)""",
        (
            contractor_id, assignment_id, project_id, amount, pay_date,
            _clean(data.get("payment_method")) or "Bank Transfer",
            _clean(data.get("reference_number")), _clean(data.get("notes")),
        ),
    )
    audit_svc.log(conn, "contractor", contractor_id, "payment", {"amount": amount})
    return get_contractor(conn, contractor_id)
