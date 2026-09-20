"""Project budget: manual lines plus the roll-up of BOQ material and Structure of Work labour."""

from backend.database import fetch_all, fetch_one

SOURCES = ("manual", "boq", "labour")


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
    stage_id = data.get("stage_id") or None
    if stage_id:
        stage = fetch_one(conn, "SELECT project_id FROM project_stages WHERE id=?", (stage_id,))
        if not stage or stage["project_id"] != data["project_id"]:
            raise ValueError("Stage not found in this project")
    cur = conn.execute(
        """INSERT INTO project_budget_lines(project_id, category_id, planned_amount,
           revision_no, is_active, notes, source, stage_id) VALUES(?,?,?,?,1,?,'manual',?)""",
        (
            data["project_id"], data["category_id"], data["planned_amount"],
            data.get("revision_no", 1), data.get("notes"), stage_id,
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
           revision_no, is_active, notes, source, stage_id) VALUES(?,?,?,?,1,?,'manual',?)""",
        (
            old["project_id"], old["category_id"], planned_amount,
            old["revision_no"] + 1, notes or old.get("notes"), old.get("stage_id"),
        ),
    )
    return fetch_one(conn, "SELECT * FROM project_budget_lines WHERE id=?", (cur.lastrowid,))


def delete_line(conn, line_id: int) -> None:
    if not fetch_one(conn, "SELECT id FROM project_budget_lines WHERE id=?", (line_id,)):
        raise ValueError("Budget line not found")
    conn.execute("UPDATE project_budget_lines SET is_active=0 WHERE id=?", (line_id,))


def delete_category(conn, category_id: int) -> None:
    if not fetch_one(conn, "SELECT id FROM budget_categories WHERE id=?", (category_id,)):
        raise ValueError("Category not found")
    if fetch_one(conn, "SELECT id FROM project_budget_lines WHERE category_id=? LIMIT 1", (category_id,)):
        raise ValueError("Category is used by budget lines")
    if fetch_one(conn, "SELECT id FROM purchase_orders WHERE budget_category_id=? LIMIT 1", (category_id,)):
        raise ValueError("Category is used by purchase orders")
    if fetch_one(conn, "SELECT id FROM project_boq_lines WHERE category_id=? LIMIT 1", (category_id,)):
        raise ValueError("Category is used by BOQ lines")
    conn.execute("DELETE FROM budget_categories WHERE id=?", (category_id,))


def _named_category(conn, names: tuple[str, ...], create_as: str, sort_order: int) -> dict:
    """Find the category the company already uses for this bucket, or make one."""
    placeholders = ",".join("?" * len(names))
    row = fetch_one(
        conn,
        f"SELECT * FROM budget_categories WHERE lower(name) IN ({placeholders}) ORDER BY id LIMIT 1",
        names,
    )
    if row:
        return row
    cur = conn.execute(
        "INSERT INTO budget_categories(name, sort_order) VALUES(?, ?)", (create_as, sort_order)
    )
    return fetch_one(conn, "SELECT * FROM budget_categories WHERE id=?", (cur.lastrowid,))


def labour_category(conn) -> dict:
    return _named_category(conn, ("labour", "labor"), "Labour", 90)


def materials_category(conn) -> dict:
    return _named_category(conn, ("materials", "material"), "Materials", 10)


def _projects_in_scope(conn, project_id: int | None) -> list[int]:
    if project_id:
        return [int(project_id)]
    rows = fetch_all(
        conn,
        """SELECT id FROM projects WHERE id IN (
             SELECT project_id FROM project_budget_lines WHERE is_active=1
             UNION SELECT project_id FROM project_boq_lines WHERE is_active=1
             UNION SELECT project_id FROM project_tasks)
           ORDER BY id""",
    )
    return [r["id"] for r in rows]


def _bucket_status(planned: int, spent: int) -> tuple[int, str]:
    pct = round(spent / planned * 100) if planned else 0
    if pct > 100:
        return pct, "Exceeded"
    if pct >= 85:
        return pct, "Near Limit"
    return pct, "Within Budget"


def summary(conn, project_id: int | None = None) -> list[dict]:
    """Planned = manual lines + BOQ material + Structure of Work labour, per category."""
    from backend.services import boq as boq_svc
    from backend.services import planning as planning_svc

    result = []
    for pid in _projects_in_scope(conn, project_id):
        project = fetch_one(conn, "SELECT id, name FROM projects WHERE id=?", (pid,))
        if not project:
            continue
        buckets: dict[int, dict] = {}

        def bucket(category_id: int, category_name: str | None = None) -> dict:
            if category_id not in buckets:
                if not category_name:
                    cat = fetch_one(conn, "SELECT name FROM budget_categories WHERE id=?", (category_id,))
                    category_name = cat["name"] if cat else "Uncategorised"
                buckets[category_id] = {
                    "project_id": pid, "project_name": project["name"],
                    "category_id": category_id, "category_name": category_name,
                    "manual_amount": 0, "boq_amount": 0, "labour_amount": 0,
                }
            return buckets[category_id]

        for line in list_lines(conn, pid):
            bucket(line["category_id"], line["category_name"])["manual_amount"] += line["planned_amount"]

        boq_amounts = boq_svc.amount_by_category(conn, pid)
        if boq_amounts:
            fallback = materials_category(conn)
            for cid, amount in boq_amounts.items():
                target = cid or fallback["id"]
                bucket(target, fallback["name"] if not cid else None)["boq_amount"] += int(amount)

        labour = planning_svc.labour_total(conn, pid)
        if labour:
            cat = labour_category(conn)
            bucket(cat["id"], cat["name"])["labour_amount"] += labour

        for row in buckets.values():
            planned = row["manual_amount"] + row["boq_amount"] + row["labour_amount"]
            actual = fetch_one(
                conn,
                """SELECT COALESCE(SUM(total),0) AS spent FROM purchase_orders
                   WHERE project_id=? AND budget_category_id=? AND status != 'cancelled'""",
                (pid, row["category_id"]),
            )
            spent = actual["spent"] if actual else 0
            pct, status = _bucket_status(planned, spent)
            row.update({
                "planned_amount": planned,
                "actual_spent": spent,
                "variance": planned - spent,
                "pct_used": pct,
                "status": status,
            })
            result.append(row)
    return result


def project_rollup(conn, project_id: int) -> dict:
    """Totals behind the Planning budget screen."""
    rows = summary(conn, project_id)
    project = fetch_one(conn, "SELECT id, name, estimated_cost FROM projects WHERE id=?", (project_id,))
    planned = sum(r["planned_amount"] for r in rows)
    spent = sum(r["actual_spent"] for r in rows)
    pct, status = _bucket_status(planned, spent)
    return {
        "project_id": project_id,
        "project_name": (project or {}).get("name"),
        "estimated_cost": (project or {}).get("estimated_cost") or 0,
        "manual_amount": sum(r["manual_amount"] for r in rows),
        "boq_amount": sum(r["boq_amount"] for r in rows),
        "labour_amount": sum(r["labour_amount"] for r in rows),
        "planned_amount": planned,
        "actual_spent": spent,
        "variance": planned - spent,
        "pct_used": pct,
        "status": status,
        "categories": rows,
    }
