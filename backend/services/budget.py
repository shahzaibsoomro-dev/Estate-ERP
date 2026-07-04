from backend.database import fetch_all, fetch_one


def list_categories(conn) -> list[dict]:
    return fetch_all(conn, "SELECT * FROM budget_categories ORDER BY sort_order, name")


def create_category(conn, name: str, sort_order: int = 0) -> dict:
    cur = conn.execute(
        "INSERT INTO budget_categories(name, sort_order) VALUES(?, ?)",
        (name, sort_order),
    )
    return fetch_one(conn, "SELECT * FROM budget_categories WHERE id=?", (cur.lastrowid,))


def list_lines(conn, project_id: int | None = None) -> list[dict]:
    q = """SELECT bl.*, bc.name AS category_name, p.name AS project_name
           FROM project_budget_lines bl
           JOIN budget_categories bc ON bc.id=bl.category_id
           JOIN projects p ON p.id=bl.project_id
           WHERE bl.is_active=1"""
    params: list = []
    if project_id:
        q += " AND bl.project_id=?"
        params.append(project_id)
    q += " ORDER BY bl.project_id, bc.sort_order"
    return fetch_all(conn, q, tuple(params))


def create_line(conn, data: dict) -> dict:
    cur = conn.execute(
        """INSERT INTO project_budget_lines(project_id, category_id, planned_amount,
           revision_no, is_active, notes) VALUES(?,?,?,?,1,?)""",
        (
            data["project_id"], data["category_id"], data["planned_amount"],
            data.get("revision_no", 1), data.get("notes"),
        ),
    )
    return fetch_one(conn, "SELECT * FROM project_budget_lines WHERE id=?", (cur.lastrowid,))


def revise_line(conn, line_id: int, planned_amount: int, notes: str | None = None) -> dict:
    old = fetch_one(conn, "SELECT * FROM project_budget_lines WHERE id=?", (line_id,))
    if not old:
        raise ValueError("Budget line not found")
    conn.execute("UPDATE project_budget_lines SET is_active=0 WHERE id=?", (line_id,))
    cur = conn.execute(
        """INSERT INTO project_budget_lines(project_id, category_id, planned_amount,
           revision_no, is_active, notes) VALUES(?,?,?,?,1,?)""",
        (
            old["project_id"], old["category_id"], planned_amount,
            old["revision_no"] + 1, notes or old.get("notes"),
        ),
    )
    return fetch_one(conn, "SELECT * FROM project_budget_lines WHERE id=?", (cur.lastrowid,))


def summary(conn, project_id: int | None = None) -> list[dict]:
    lines = list_lines(conn, project_id)
    result = []
    for line in lines:
        actual = fetch_one(
            conn,
            """SELECT COALESCE(SUM(total),0) AS spent FROM purchase_orders
               WHERE project_id=? AND budget_category_id=?""",
            (line["project_id"], line["category_id"]),
        )
        spent = actual["spent"] if actual else 0
        planned = line["planned_amount"]
        variance = planned - spent
        pct = round(spent / planned * 100) if planned else 0
        if pct > 100:
            bstatus = "Exceeded"
        elif pct >= 85:
            bstatus = "Near Limit"
        else:
            bstatus = "Within Budget"
        result.append({
            "project_id": line["project_id"],
            "project_name": line["project_name"],
            "category_id": line["category_id"],
            "category_name": line["category_name"],
            "planned_amount": planned,
            "actual_spent": spent,
            "variance": variance,
            "pct_used": pct,
            "status": bstatus,
        })
    return result
