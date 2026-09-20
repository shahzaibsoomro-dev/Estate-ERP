from datetime import date
from collections import defaultdict

from backend.database import fetch_all, fetch_one


def _clean(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _money(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def cash_position(conn, project_ids: list[int] | None = None) -> dict:
    """Cash in hand + bank from the journal (optionally one set of projects)."""
    from backend.services import journal as journal_svc
    entries = journal_svc.build(conn, project_ids, end=date.today().isoformat())
    t = journal_svc.totals(entries)
    cash = journal_svc.signed("1010", *t.get("1010", [0, 0]))
    bank = journal_svc.signed("1020", *t.get("1020", [0, 0]))
    has_opening = bool(fetch_one(
        conn,
        """SELECT id FROM ledger_entries
           WHERE COALESCE(kind,'') IN ('opening','adjust')
              OR lower(COALESCE(category,'')) LIKE 'opening%'
           LIMIT 1""",
    ))
    return {"cash": cash, "bank": bank, "current": cash + bank, "has_opening": has_opening}


def list_cashbook(conn, project_ids: list[int] | None = None) -> dict:
    inflows = fetch_all(
        conn,
        """SELECT p.id AS source_id, p.payment_date AS entry_date,
                  'Collection · ' || c.name || ' · ' || COALESCE(b.booking_no,'') AS narration,
                  p.amount AS inflow, 0 AS outflow, 'customer' AS source, NULL AS id,
                  b.project_id AS project_id
           FROM payments p
           JOIN customers c ON c.id=p.customer_id
           LEFT JOIN bookings b ON b.id=p.booking_id
           WHERE NOT EXISTS (
             SELECT 1 FROM hold_token_applications hta WHERE hta.payment_id=p.id
           )""",
    )
    hold_in = fetch_all(
        conn,
        """SELECT ht.id AS source_id, ht.txn_date AS entry_date,
                  'Hold token · ' || COALESCE(c.name,'Customer') || ' · ' || u.unit_no
                    || COALESCE(' · ' || hr.receipt_no,'') AS narration,
                  ht.amount AS inflow, 0 AS outflow, 'hold' AS source, NULL AS id,
                  hr.receipt_no AS receipt_no, u.project_id AS project_id
           FROM hold_transactions ht
           JOIN unit_holds h ON h.id=ht.hold_id
           JOIN units u ON u.id=h.unit_id
           LEFT JOIN customers c ON c.id=h.customer_id
           LEFT JOIN hold_receipts hr ON hr.transaction_id=ht.id
           WHERE ht.direction='in' AND ht.amount > 0""",
    )
    hold_out = fetch_all(
        conn,
        """SELECT ht.id AS source_id, ht.txn_date AS entry_date,
                  'Hold refund · ' || COALESCE(c.name,'Customer') || ' · ' || u.unit_no
                    || COALESCE(' · ' || ht.voucher_no,'') AS narration,
                  0 AS inflow, ht.amount AS outflow, 'hold' AS source, NULL AS id,
                  ht.voucher_no AS receipt_no, u.project_id AS project_id
           FROM hold_transactions ht
           JOIN unit_holds h ON h.id=ht.hold_id
           JOIN units u ON u.id=h.unit_id
           LEFT JOIN customers c ON c.id=h.customer_id
           WHERE ht.direction='refund' AND ht.amount > 0""",
    )
    vendor_out = fetch_all(
        conn,
        """SELECT vp.id AS source_id, vp.payment_date AS entry_date,
                  'Vendor · ' || v.name || COALESCE(' · ' || po.po_no,'') AS narration,
                  CASE WHEN vp.amount < 0 THEN -vp.amount ELSE 0 END AS inflow,
                  CASE WHEN vp.amount > 0 THEN vp.amount ELSE 0 END AS outflow,
                  'vendor' AS source, NULL AS id, po.project_id AS project_id
           FROM vendor_payments vp
           JOIN vendors v ON v.id=vp.vendor_id
           LEFT JOIN purchase_orders po ON po.id=vp.purchase_order_id""",
    )
    agent_out = fetch_all(
        conn,
        """SELECT acp.id AS source_id, acp.payment_date AS entry_date,
                  'Agent · ' || a.name || COALESCE(' · ' || b.booking_no,'') AS narration,
                  0 AS inflow, acp.amount AS outflow, 'agent' AS source, NULL AS id,
                  b.project_id AS project_id
           FROM agent_commission_payments acp
           JOIN agent_commissions ac ON ac.id=acp.commission_id
           JOIN agents a ON a.id=ac.agent_id
           LEFT JOIN bookings b ON b.id=ac.booking_id""",
    )
    agent_bonus_out = fetch_all(
        conn,
        """SELECT ab.id AS source_id, ab.bonus_date AS entry_date,
                  'Agent bonus · ' || a.name || COALESCE(' · ' || ab.reason,'') AS narration,
                  0 AS inflow, ab.amount AS outflow, 'agent_bonus' AS source, NULL AS id,
                  NULL AS project_id
           FROM agent_bonuses ab
           JOIN agents a ON a.id=ab.agent_id""",
    )
    inv_in = fetch_all(
        conn,
        """SELECT ic.id AS source_id, ic.contribution_date AS entry_date,
                  'Investor in · ' || inv.name AS narration,
                  ic.amount AS inflow, 0 AS outflow, 'investor' AS source, NULL AS id,
                  a.project_id AS project_id
           FROM investor_contributions ic
           JOIN investor_agreements a ON a.id=ic.agreement_id
           JOIN investors inv ON inv.id=a.investor_id""",
    )
    inv_out = fetch_all(
        conn,
        """SELECT d.id AS source_id, d.distribution_date AS entry_date,
                  'Investor out · ' || inv.name AS narration,
                  0 AS inflow, d.amount AS outflow, 'investor' AS source, NULL AS id,
                  a.project_id AS project_id
           FROM investor_distributions d
           JOIN investor_agreements a ON a.id=d.agreement_id
           JOIN investors inv ON inv.id=a.investor_id""",
    )
    partner_in = fetch_all(
        conn,
        """SELECT pc.id AS source_id, pc.contribution_date AS entry_date,
                  'Partner in · ' || p.name AS narration,
                  pc.amount AS inflow, 0 AS outflow, 'partner' AS source, NULL AS id,
                  a.project_id AS project_id
           FROM partner_contributions pc
           JOIN partner_agreements a ON a.id=pc.agreement_id
           JOIN partners p ON p.id=a.partner_id""",
    )
    partner_out = fetch_all(
        conn,
        """SELECT d.id AS source_id, d.distribution_date AS entry_date,
                  'Partner out · ' || p.name AS narration,
                  0 AS inflow, d.amount AS outflow, 'partner' AS source, NULL AS id,
                  a.project_id AS project_id
           FROM partner_distributions d
           JOIN partner_agreements a ON a.id=d.agreement_id
           JOIN partners p ON p.id=a.partner_id""",
    )
    contractor_out = []
    try:
        contractor_out = fetch_all(
            conn,
            """SELECT cp.id AS source_id, cp.payment_date AS entry_date,
                      'Contractor · ' || c.name || COALESCE(' · ' || p.name,'') AS narration,
                      0 AS inflow, cp.amount AS outflow, 'contractor' AS source, NULL AS id,
                      cp.project_id AS project_id
               FROM contractor_payments cp
               JOIN contractors c ON c.id=cp.contractor_id
               LEFT JOIN projects p ON p.id=cp.project_id""",
        )
    except Exception:
        contractor_out = []
    cancel_out = fetch_all(
        conn,
        """SELECT bc.id AS source_id, date(bc.cancelled_at) AS entry_date,
                  'Cancel refund · ' || c.name || ' · ' || COALESCE(b.booking_no,'') AS narration,
                  0 AS inflow, bc.refund_amount AS outflow, 'cancel' AS source, NULL AS id,
                  b.project_id AS project_id
           FROM booking_cancellations bc
           JOIN bookings b ON b.id=bc.booking_id
           JOIN customers c ON c.id=b.customer_id
           WHERE bc.refund_amount > 0""",
    )
    transfer_in = []
    try:
        transfer_in = fetch_all(
            conn,
            """SELECT bt.id AS source_id, bt.transfer_date AS entry_date,
                      'Transfer fee · ' || u.unit_no || ' · ' || c.name AS narration,
                      bt.transfer_fee AS inflow, 0 AS outflow, 'transfer_fee' AS source, NULL AS id,
                      b.project_id AS project_id
               FROM booking_transfers bt
               JOIN bookings b ON b.id=bt.booking_id
               JOIN units u ON u.id=b.unit_id
               JOIN customers c ON c.id=bt.to_customer_id
               WHERE COALESCE(bt.transfer_fee, 0) > 0""",
        )
    except Exception:
        transfer_in = []
    manual = fetch_all(
        conn,
        """SELECT id AS source_id, entry_date, narration,
                  CASE WHEN direction='in' THEN amount ELSE 0 END AS inflow,
                  CASE WHEN direction='out' THEN amount ELSE 0 END AS outflow,
                  CASE WHEN COALESCE(kind,'') IN ('opening','adjust') THEN kind ELSE 'manual' END AS source,
                  id, project_id
           FROM ledger_entries""",
    )
    rows = []
    for group in (inflows, hold_in, hold_out, vendor_out, agent_out, agent_bonus_out, inv_in, inv_out,
                  partner_in, partner_out, contractor_out, cancel_out, transfer_in, manual):
        rows.extend(group)
    if project_ids is not None:
        allowed = set(project_ids)
        rows = [r for r in rows if r.get("project_id") in allowed]
    names = {p["id"]: p["name"] for p in fetch_all(conn, "SELECT id, name FROM projects")}
    rows.sort(key=lambda r: (r.get("entry_date") or "", r.get("source") or "", r.get("source_id") or 0))
    balance = 0
    inflow = 0
    outflow = 0
    by_proj = defaultdict(lambda: {"inflow": 0, "outflow": 0})
    for r in rows:
        inn = _money(r.get("inflow"))
        out = _money(r.get("outflow"))
        inflow += inn
        outflow += out
        balance += inn - out
        r["balance"] = balance
        r["inflow"] = inn
        r["outflow"] = out
        pid = r.get("project_id")
        r["project_name"] = names.get(pid) or ("Company-wide" if pid is None else "—")
        key = pid if pid is not None else 0
        by_proj[key]["inflow"] += inn
        by_proj[key]["outflow"] += out
        by_proj[key]["project_id"] = pid
        by_proj[key]["project_name"] = r["project_name"]
    rows.reverse()
    position = cash_position(conn, project_ids)
    projects = []
    for row in by_proj.values():
        row["net"] = row["inflow"] - row["outflow"]
        projects.append(row)
    projects.sort(key=lambda x: x["project_name"] or "")
    return {
        "inflow": inflow,
        "outflow": outflow,
        "net": inflow - outflow,
        "revenue": inflow,
        "expenses": outflow,
        "profit": inflow - outflow,
        "cash": position["cash"],
        "bank": position["bank"],
        "current": position["current"],
        "has_opening": position["has_opening"],
        "filtered": project_ids is not None,
        "by_project": projects,
        "entries": rows,
    }


def create_ledger_entry(conn, data: dict) -> dict:
    narration = _clean(data.get("narration"))
    entry_date = _clean(data.get("entry_date"))
    if not narration or not entry_date:
        raise ValueError("Date and narration are required")
    direction = (_clean(data.get("direction")) or "").lower()
    if direction not in ("in", "out"):
        debit = int(data.get("debit") or 0)
        credit = int(data.get("credit") or 0)
        if debit > 0 and credit <= 0:
            direction = "out"
            amount = debit
        elif credit > 0:
            direction = "in"
            amount = credit
        else:
            raise ValueError("Choose money in or money out")
    else:
        amount = int(data.get("amount") or 0)
    if amount <= 0:
        raise ValueError("Amount must be greater than 0")
    category = _clean(data.get("category") or data.get("account_type"))
    try:
        date.fromisoformat(entry_date)
    except ValueError as e:
        raise ValueError("Date must be YYYY-MM-DD") from e
    method = _clean(data.get("payment_method")) or "Bank"
    if method.lower() not in ("cash", "bank", "bank transfer", "cheque", "online transfer"):
        raise ValueError("Paid from must be Cash or Bank")
    project_id = data.get("project_id") or None
    if project_id and not fetch_one(conn, "SELECT id FROM projects WHERE id=?", (project_id,)):
        raise ValueError("Project not found")
    kind = (_clean(data.get("kind")) or "manual").lower()
    if kind not in ("manual", "opening", "adjust"):
        kind = "manual"
    cur = conn.execute(
        """INSERT INTO ledger_entries(entry_date, narration, amount, direction, category, notes,
                                       payment_method, project_id, kind)
           VALUES(?,?,?,?,?,?,?,?,?)""",
        (entry_date, narration, amount, direction, category, _clean(data.get("notes")), method, project_id, kind),
    )
    return fetch_one(conn, "SELECT * FROM ledger_entries WHERE id=?", (cur.lastrowid,))


def set_current_balance(conn, data: dict, *, allow_noop: bool = False) -> dict:
    """Bring cash/bank books to the amounts the owner states.

    First time this is used it posts an opening balance. Later changes post
    adjustments so the running balance matches the till / bank, with a trail.
    """
    cash = _money(data.get("cash"))
    bank = _money(data.get("bank"))
    if cash < 0 or bank < 0:
        raise ValueError("Cash and bank cannot be negative")
    as_of = _clean(data.get("as_of") or data.get("entry_date")) or date.today().isoformat()
    try:
        date.fromisoformat(as_of)
    except ValueError as e:
        raise ValueError("Date must be YYYY-MM-DD") from e
    reason = _clean(data.get("reason") or data.get("notes"))
    now = cash_position(conn)
    kind = "opening" if not now["has_opening"] else "adjust"
    posted = []
    for method, target, current in (("Cash", cash, now["cash"]), ("Bank", bank, now["bank"])):
        delta = target - current
        if delta == 0:
            continue
        label = "Opening balance" if kind == "opening" else "Balance adjustment"
        nar = f"{label} · {method}"
        if reason:
            nar += f" · {reason}"
        posted.append(create_ledger_entry(conn, {
            "entry_date": as_of,
            "narration": nar,
            "amount": abs(delta),
            "direction": "in" if delta > 0 else "out",
            "category": label,
            "payment_method": method,
            "kind": kind,
            "notes": reason,
            "project_id": None,
        }))
    if not posted and not allow_noop:
        raise ValueError("Already at that cash and bank balance")
    return {**cash_position(conn), "posted": posted, "kind": kind}


def delete_ledger_entry(conn, entry_id: int) -> None:
    if not fetch_one(conn, "SELECT id FROM ledger_entries WHERE id=?", (entry_id,)):
        raise ValueError("Entry not found")
    conn.execute("DELETE FROM ledger_entries WHERE id=?", (entry_id,))
