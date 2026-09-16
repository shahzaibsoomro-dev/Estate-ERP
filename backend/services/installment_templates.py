"""Project construction-milestone installment templates."""

from datetime import date, timedelta

from backend.database import fetch_all, fetch_one


def _clean(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def validate_rules(rules: list[dict]) -> list[dict]:
    if not rules:
        raise ValueError("Template requires at least one rule")
    cleaned = []
    total_bps = 0
    progresses = []
    for i, raw in enumerate(rules):
        label = _clean(raw.get("label")) or f"Installment {i + 1}"
        bps = _int(raw.get("amount_bps"))
        if bps <= 0:
            raise ValueError(f"Rule '{label}' must have a positive percentage")
        trigger_kind = (_clean(raw.get("trigger_kind")) or "construction").lower()
        if trigger_kind not in ("construction", "time"):
            raise ValueError(f"Invalid trigger kind for '{label}'")
        progress = raw.get("milestone_progress")
        if progress is None:
            progress = raw.get("trigger_progress")
        progress = None if progress in (None, "") else _int(progress)
        if trigger_kind == "construction":
            if progress is None or progress < 0 or progress > 100:
                raise ValueError(f"Rule '{label}' needs a progress threshold 0–100")
            progresses.append(progress)
        due_days = max(_int(raw.get("due_days_after_trigger"), 0), 0)
        cleaned.append({
            "sort_order": i + 1,
            "label": label,
            "trigger_kind": trigger_kind,
            "amount_bps": bps,
            "installment_count": max(_int(raw.get("installment_count"), 1), 1),
            "start_offset_months": max(_int(raw.get("start_offset_months"), 0), 0),
            "interval_months": max(_int(raw.get("interval_months"), 1), 1),
            "milestone_progress": progress,
            "forecast_due_date": _clean(raw.get("forecast_due_date")),
            "due_days_after_trigger": due_days,
            "notes": _clean(raw.get("notes")),
        })
        total_bps += bps
    if total_bps != 10000:
        raise ValueError(
            f"Rule percentages must total exactly 100% of financed balance (got {total_bps / 100:.2f}%)"
        )
    if len(progresses) != len(set(progresses)):
        raise ValueError("Construction progress thresholds must be unique")
    if progresses != sorted(progresses):
        raise ValueError("Construction progress thresholds must be in increasing order")
    return cleaned


def list_pay_plans(conn) -> list[dict]:
    """All projects with their active installment template (pay plan) summary."""
    projects = fetch_all(conn, "SELECT id, name, status FROM projects ORDER BY name")
    out = []
    for p in projects:
        tmpl = get_active_template(conn, p["id"])
        rules = (tmpl or {}).get("rules") or []
        out.append({
            "project_id": p["id"],
            "project_name": p["name"],
            "project_status": p.get("status"),
            "has_template": bool(tmpl),
            "template_id": (tmpl or {}).get("id"),
            "template_name": (tmpl or {}).get("name"),
            "revision": (tmpl or {}).get("revision"),
            "default_booking_bps": (tmpl or {}).get("default_booking_bps"),
            "rule_count": len(rules),
            "rules": rules,
        })
    return out


def get_active_template(conn, project_id: int) -> dict | None:
    tmpl = fetch_one(
        conn,
        """SELECT * FROM project_installment_templates
           WHERE project_id=? AND is_active=1
           ORDER BY id DESC LIMIT 1""",
        (project_id,),
    )
    if not tmpl:
        return None
    return _with_rules(conn, tmpl)


def get_template(conn, template_id: int) -> dict | None:
    tmpl = fetch_one(conn, "SELECT * FROM project_installment_templates WHERE id=?", (template_id,))
    if not tmpl:
        return None
    return _with_rules(conn, tmpl)


def _with_rules(conn, tmpl: dict) -> dict:
    out = dict(tmpl)
    out["rules"] = fetch_all(
        conn,
        """SELECT * FROM project_installment_template_rules
           WHERE template_id=? ORDER BY sort_order, id""",
        (tmpl["id"],),
    )
    return out


def save_template(conn, project_id: int, data: dict) -> dict:
    if not fetch_one(conn, "SELECT id FROM projects WHERE id=?", (project_id,)):
        raise ValueError("Project not found")
    name = _clean(data.get("name")) or "Construction installment plan"
    rules = validate_rules(data.get("rules") or [])
    default_booking_bps = _int(data.get("default_booking_bps"), 1000)
    if default_booking_bps < 0 or default_booking_bps > 10000:
        raise ValueError("Default booking percentage must be between 0 and 100")

    existing = fetch_one(
        conn,
        """SELECT * FROM project_installment_templates
           WHERE project_id=? AND is_active=1 ORDER BY id DESC LIMIT 1""",
        (project_id,),
    )
    revision = 1
    if existing:
        revision = int(existing.get("revision") or 1) + 1
        conn.execute(
            "UPDATE project_installment_templates SET is_active=0, updated_at=datetime('now') WHERE id=?",
            (existing["id"],),
        )

    cur = conn.execute(
        """INSERT INTO project_installment_templates(
             project_id, name, default_booking_bps, revision, is_active)
           VALUES(?,?,?,?,1)""",
        (project_id, name, default_booking_bps, revision),
    )
    template_id = cur.lastrowid
    for rule in rules:
        conn.execute(
            """INSERT INTO project_installment_template_rules(
                 template_id, sort_order, label, trigger_kind, amount_bps,
                 installment_count, start_offset_months, interval_months,
                 milestone_progress, forecast_due_date, due_days_after_trigger, notes)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                template_id, rule["sort_order"], rule["label"], rule["trigger_kind"],
                rule["amount_bps"], rule["installment_count"], rule["start_offset_months"],
                rule["interval_months"], rule["milestone_progress"], rule["forecast_due_date"],
                rule["due_days_after_trigger"], rule["notes"],
            ),
        )
    return get_template(conn, template_id)


def delete_active_template(conn, project_id: int) -> None:
    conn.execute(
        """UPDATE project_installment_templates SET is_active=0, updated_at=datetime('now')
           WHERE project_id=? AND is_active=1""",
        (project_id,),
    )


def _split_amounts(financed: int, rules: list[dict]) -> list[int]:
    if financed <= 0:
        raise ValueError("Financed balance (sale price − booking amount) must be positive")
    amounts = []
    allocated = 0
    for i, rule in enumerate(rules):
        if i == len(rules) - 1:
            amt = financed - allocated
        else:
            amt = int(financed * rule["amount_bps"] // 10000)
        if amt <= 0:
            raise ValueError(f"Generated amount for '{rule['label']}' must be positive")
        amounts.append(amt)
        allocated += amt
    return amounts


def _add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    y += d.year
    m += 1
    last = [31, 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return date(y, m, min(d.day, last))


def preview_plan(conn, project_id: int, sale_price: int, booking_amount: int,
                 template_id: int | None = None, booking_date: str | None = None) -> dict:
    sale_price = _int(sale_price)
    booking_amount = max(_int(booking_amount), 0)
    if sale_price <= 0:
        raise ValueError("Sale price must be positive")
    if booking_amount >= sale_price:
        raise ValueError("Booking amount must be less than sale price")
    financed = sale_price - booking_amount

    if template_id:
        tmpl = get_template(conn, template_id)
        if not tmpl or int(tmpl["project_id"]) != int(project_id):
            raise ValueError("Template not found for this project")
    else:
        tmpl = get_active_template(conn, project_id)
        if not tmpl:
            raise ValueError("No active installment template for this project")

    rules = tmpl["rules"]
    amounts = _split_amounts(financed, rules)
    try:
        start = date.fromisoformat(booking_date) if booking_date else date.today()
    except ValueError as e:
        raise ValueError("Booking date must be YYYY-MM-DD") from e
    installments = []
    for rule, rule_amt in zip(rules, amounts):
        trigger_kind = rule["trigger_kind"]
        count = max(int(rule.get("installment_count") or 1), 1)
        interval = max(int(rule.get("interval_months") or 1), 1)
        offset = int(rule.get("start_offset_months") or 0)
        each = rule_amt // count
        for k in range(count):
            amt = each if k < count - 1 else rule_amt - each * (count - 1)
            if amt <= 0:
                raise ValueError(f"'{rule['label']}' is too small to split into {count} installments")
            forecast = rule.get("forecast_due_date") if count == 1 else None
            if not forecast and trigger_kind == "time":
                forecast = _add_months(start, offset + k * interval).isoformat()
            label = rule["label"] if count == 1 else f"{rule['label']} {k + 1}/{count}"
            installments.append({
                "label": label,
                "type": rule["label"],
                "amount": amt,
                "amount_bps": rule["amount_bps"] if count == 1 else None,
                "trigger_kind": trigger_kind,
                "trigger_progress": rule.get("milestone_progress"),
                "milestone_progress": rule.get("milestone_progress"),
                "forecast_due_date": forecast,
                "due_date": forecast or start.isoformat(),
                "due_days_after_trigger": rule.get("due_days_after_trigger") or 0,
                "trigger_label": label,
                "template_rule_id": rule["id"],
                "status": "scheduled" if trigger_kind == "construction" else "pending",
                "notes": rule.get("notes") or "",
            })
    return {
        "template_id": tmpl["id"],
        "template_revision": tmpl["revision"],
        "template_name": tmpl["name"],
        "plan_source": "template",
        "sale_price": sale_price,
        "booking_amount": booking_amount,
        "financed": financed,
        "installments": installments,
    }


def preview_for_booking(conn, project_id: int, sale_price: int, booking_amount: int,
                        template_id: int | None = None, booking_date: str | None = None) -> dict:
    return preview_plan(conn, project_id, sale_price, booking_amount, template_id, booking_date)


def activate_milestones_for_project(conn, project_id: int, progress: int,
                                    progress_date: str | None = None) -> int:
    """Activate scheduled construction installments whose threshold is reached."""
    progress = max(0, min(100, _int(progress)))
    when = _clean(progress_date) or date.today().isoformat()
    rows = fetch_all(
        conn,
        """SELECT i.* FROM installments i
           JOIN bookings b ON b.id=i.booking_id
           WHERE b.project_id=? AND b.status='active'
             AND i.status='scheduled'
             AND i.trigger_kind='construction'
             AND i.trigger_progress IS NOT NULL
             AND i.trigger_progress <= ?""",
        (project_id, progress),
    )
    activated = 0
    for r in rows:
        grace = int(r.get("due_days_after_trigger") or 0)
        due = (date.fromisoformat(when) + timedelta(days=grace)).isoformat()
        conn.execute(
            """UPDATE installments SET status='pending', due_date=?, activated_at=?
               WHERE id=? AND status='scheduled'""",
            (due, when, r["id"]),
        )
        activated += 1
    return activated
