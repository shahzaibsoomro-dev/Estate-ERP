from backend.database import fetch_all, fetch_one


def _clean(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def list_cashbook(conn) -> dict:
    inflows = fetch_all(
        conn,
        """SELECT p.id AS source_id, p.payment_date AS entry_date,
                  'Collection · ' || c.name || ' · ' || COALESCE(b.booking_no,'') AS narration,
                  p.amount AS inflow, 0 AS outflow, 'customer' AS source, NULL AS id
           FROM payments p
           JOIN customers c ON c.id=p.customer_id
           LEFT JOIN bookings b ON b.id=p.booking_id""",
    )
    vendor_out = fetch_all(
        conn,
        """SELECT vp.id AS source_id, vp.payment_date AS entry_date,
                  'Vendor · ' || v.name || COALESCE(' · ' || po.po_no,'') AS narration,
                  0 AS inflow, vp.amount AS outflow, 'vendor' AS source, NULL AS id
           FROM vendor_payments vp
           JOIN vendors v ON v.id=vp.vendor_id
           LEFT JOIN purchase_orders po ON po.id=vp.purchase_order_id""",
    )
    agent_out = fetch_all(
        conn,
        """SELECT acp.id AS source_id, acp.payment_date AS entry_date,
                  'Agent · ' || a.name || COALESCE(' · ' || b.booking_no,'') AS narration,
                  0 AS inflow, acp.amount AS outflow, 'agent' AS source, NULL AS id
           FROM agent_commission_payments acp
           JOIN agent_commissions ac ON ac.id=acp.commission_id
           JOIN agents a ON a.id=ac.agent_id
           LEFT JOIN bookings b ON b.id=ac.booking_id""",
    )
    inv_in = fetch_all(
        conn,
        """SELECT ic.id AS source_id, ic.contribution_date AS entry_date,
                  'Investor in · ' || inv.name AS narration,
                  ic.amount AS inflow, 0 AS outflow, 'investor' AS source, NULL AS id
           FROM investor_contributions ic
           JOIN investor_agreements a ON a.id=ic.agreement_id
           JOIN investors inv ON inv.id=a.investor_id""",
    )
    inv_out = fetch_all(
        conn,
        """SELECT d.id AS source_id, d.distribution_date AS entry_date,
                  'Investor out · ' || inv.name AS narration,
                  0 AS inflow, d.amount AS outflow, 'investor' AS source, NULL AS id
           FROM investor_distributions d
           JOIN investor_agreements a ON a.id=d.agreement_id
           JOIN investors inv ON inv.id=a.investor_id""",
    )
    manual = fetch_all(
        conn,
        """SELECT id AS source_id, entry_date, narration,
                  CASE WHEN direction='in' THEN amount ELSE 0 END AS inflow,
                  CASE WHEN direction='out' THEN amount ELSE 0 END AS outflow,
                  'manual' AS source, id
           FROM ledger_entries""",
    )
    rows = []
    for group in (inflows, vendor_out, agent_out, inv_in, inv_out, manual):
        rows.extend(group)
    rows.sort(key=lambda r: (r.get("entry_date") or "", r.get("source") or "", r.get("source_id") or 0))
    balance = 0
    inflow = 0
    outflow = 0
    for r in rows:
        inn = int(r.get("inflow") or 0)
        out = int(r.get("outflow") or 0)
        inflow += inn
        outflow += out
        balance += inn - out
        r["balance"] = balance
        r["inflow"] = inn
        r["outflow"] = out
    rows.reverse()
    return {
        "inflow": inflow,
        "outflow": outflow,
        "net": inflow - outflow,
        "revenue": inflow,
        "expenses": outflow,
        "profit": inflow - outflow,
        "entries": rows,
    }


def create_ledger_entry(conn, data: dict) -> dict:
    narration = _clean(data.get("narration"))
    entry_date = _clean(data.get("entry_date"))
    if not narration or not entry_date:
        raise ValueError("Date and narration are required")
    direction = (_clean(data.get("direction")) or "").lower()
    if direction not in ("in", "out"):
        # legacy debit/credit from old form
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
    cur = conn.execute(
        """INSERT INTO ledger_entries(entry_date, narration, amount, direction, category, notes)
           VALUES(?,?,?,?,?,?)""",
        (entry_date, narration, amount, direction, category, _clean(data.get("notes"))),
    )
    return fetch_one(conn, "SELECT * FROM ledger_entries WHERE id=?", (cur.lastrowid,))


def delete_ledger_entry(conn, entry_id: int) -> None:
    if not fetch_one(conn, "SELECT id FROM ledger_entries WHERE id=?", (entry_id,)):
        raise ValueError("Entry not found")
    conn.execute("DELETE FROM ledger_entries WHERE id=?", (entry_id,))
