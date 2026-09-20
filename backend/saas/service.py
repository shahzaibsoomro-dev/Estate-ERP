"""Companies, plans, subscriptions and subscription payments (platform database)."""
import json
import os
import re
import sqlite3
from calendar import monthrange
from datetime import date, timedelta

from backend.auth.context import current_ip, current_user_id
from backend.config import BASE_DIR, DB_PATH, TENANTS_DIR
from backend.database import fetch_all, fetch_one
from backend.saas.phone import normalize_email, normalize_phone

STATE_LABELS = {
    "trial": "Trial",
    "active": "Active",
    "grace": "Payment overdue (grace period)",
    "expired": "Expired — read-only",
    "suspended": "Suspended",
    "none": "No subscription",
}
PAYMENT_METHODS = ("Bank transfer", "Cash", "Cheque", "JazzCash", "Easypaisa", "Card", "Other")


# ------------------------------------------------------------------ helpers
def audit(conn, action: str, *, company_id: int | None = None, target_type: str | None = None,
          target_id: int | None = None, details: dict | None = None, user_id: int | None = None) -> None:
    conn.execute(
        """INSERT INTO platform_audit(user_id, company_id, action, target_type, target_id, details, ip)
           VALUES(?,?,?,?,?,?,?)""",
        (user_id if user_id is not None else current_user_id.get(), company_id, action,
         target_type, target_id, json.dumps(details or {}), current_ip.get()),
    )


def add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, min(d.day, monthrange(y, m)[1]))


def _d(s) -> date:
    return date.fromisoformat(str(s)[:10])


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s[:40] or "company"


def resolve_db_path(stored: str) -> str:
    return stored if os.path.isabs(stored) else os.path.join(BASE_DIR, stored)


def _store_db_path(path: str) -> str:
    try:
        rel = os.path.relpath(path, BASE_DIR)
    except ValueError:
        return path
    return path if rel.startswith("..") else rel


# ------------------------------------------------------------------ subscription state
def subscription_state(company: dict, sub: dict | None, today: date | None = None) -> dict:
    today = today or date.today()
    if company.get("status") == "suspended":
        state = "suspended"
    elif not sub:
        state = "none"
    else:
        end = _d(sub["current_period_end"])
        if today <= end:
            state = "trial" if sub.get("is_trial") else "active"
        elif today <= end + timedelta(days=sub.get("grace_days") or 0):
            state = "grace"
        else:
            state = "expired"
    out = {"state": state, "label": STATE_LABELS[state], "read_only": state in ("expired", "none"),
           "staff_blocked": state == "suspended"}
    if sub:
        end = _d(sub["current_period_end"])
        out["period_end"] = sub["current_period_end"]
        out["days_left"] = (end - today).days
        out["grace_ends"] = (end + timedelta(days=sub.get("grace_days") or 0)).isoformat()
        out["warn"] = state in ("grace",) or (state in ("active", "trial") and out["days_left"] <= 7)
    else:
        out["warn"] = True
    return out


# ------------------------------------------------------------------ plans
def list_plans(conn, active_only: bool = False) -> list[dict]:
    sql = "SELECT * FROM plans"
    if active_only:
        sql += " WHERE is_active=1"
    return fetch_all(conn, sql + " ORDER BY sort_order, price_monthly")


def save_plan(conn, plan_id: int | None, data: dict) -> dict:
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("Plan name is required")
    vals = (name, int(data.get("price_monthly") or 0), int(data.get("price_yearly") or 0),
            data.get("max_employees"), data.get("max_projects"), data.get("description"),
            int(bool(data.get("is_active", True))))
    if plan_id is None:
        code = slugify(data.get("code") or name)
        try:
            cur = conn.execute(
                """INSERT INTO plans(name, price_monthly, price_yearly, max_employees, max_projects,
                                     description, is_active, code, sort_order)
                   VALUES(?,?,?,?,?,?,?,?, (SELECT COALESCE(MAX(sort_order),0)+1 FROM plans))""",
                (*vals, code),
            )
        except sqlite3.IntegrityError as e:
            raise ValueError("A plan with this code already exists") from e
        plan_id = cur.lastrowid
    else:
        if not fetch_one(conn, "SELECT id FROM plans WHERE id=?", (plan_id,)):
            raise LookupError("Plan not found")
        conn.execute(
            """UPDATE plans SET name=?, price_monthly=?, price_yearly=?, max_employees=?, max_projects=?,
                      description=?, is_active=? WHERE id=?""",
            (*vals, plan_id),
        )
    audit(conn, "plan.save", target_type="plan", target_id=plan_id, details={"name": name})
    return fetch_one(conn, "SELECT * FROM plans WHERE id=?", (plan_id,))


# ------------------------------------------------------------------ companies
def get_company(conn, company_id: int) -> dict | None:
    return fetch_one(conn, "SELECT * FROM companies WHERE id=?", (company_id,))


def get_subscription(conn, company_id: int) -> dict | None:
    return fetch_one(
        conn,
        """SELECT s.*, p.name AS plan_name, p.code AS plan_code, p.max_employees, p.max_projects,
                  p.price_monthly, p.price_yearly
           FROM subscriptions s JOIN plans p ON p.id=s.plan_id WHERE s.company_id=?""",
        (company_id,),
    )


def company_state(conn, company_id: int) -> dict:
    c = get_company(conn, company_id)
    if not c:
        raise LookupError("Company not found")
    return subscription_state(c, get_subscription(conn, company_id))


def _tenant_counts(company: dict) -> dict:
    path = resolve_db_path(company["db_path"])
    if not os.path.exists(path):
        return {"projects": 0, "units": 0, "customers": 0, "bookings": 0}
    conn = sqlite3.connect(path)
    try:
        q = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
        return {
            "projects": q("SELECT COUNT(*) FROM projects"),
            "units": q("SELECT COUNT(*) FROM units"),
            "customers": q("SELECT COUNT(*) FROM customers"),
            "bookings": q("SELECT COUNT(*) FROM bookings WHERE status='active'"),
        }
    except sqlite3.Error:
        return {"projects": 0, "units": 0, "customers": 0, "bookings": 0}
    finally:
        conn.close()


def list_companies(conn) -> list[dict]:
    rows = fetch_all(
        conn,
        """SELECT c.*, s.plan_id, s.billing_cycle, s.amount, s.is_trial, s.current_period_end, s.grace_days,
                  s.started_on, p.name AS plan_name,
                  (SELECT COUNT(*) FROM users u WHERE u.company_id=c.id AND u.role='admin') AS admins,
                  (SELECT COUNT(*) FROM users u WHERE u.company_id=c.id AND u.role='employee') AS employees,
                  (SELECT COUNT(*) FROM users u WHERE u.company_id=c.id AND u.role='customer') AS customer_logins,
                  (SELECT MAX(last_login_at) FROM users u WHERE u.company_id=c.id AND u.role!='customer') AS last_staff_login,
                  (SELECT COALESCE(SUM(amount),0) FROM subscription_payments sp
                    WHERE sp.company_id=c.id AND sp.voided_at IS NULL) AS total_paid,
                  (SELECT MAX(paid_on) FROM subscription_payments sp
                    WHERE sp.company_id=c.id AND sp.voided_at IS NULL) AS last_paid_on
           FROM companies c
           LEFT JOIN subscriptions s ON s.company_id=c.id
           LEFT JOIN plans p ON p.id=s.plan_id
           ORDER BY c.name""",
    )
    for r in rows:
        sub = r if r.get("plan_id") else None
        r["subscription"] = subscription_state(r, sub)
        r.pop("db_path", None)
    return rows


def company_detail(conn, company_id: int) -> dict:
    c = get_company(conn, company_id)
    if not c:
        raise LookupError("Company not found")
    sub = get_subscription(conn, company_id)
    out = dict(c)
    out["counts"] = _tenant_counts(c)
    out.pop("db_path", None)
    out["subscription"] = sub
    out["state"] = subscription_state(c, sub)
    out["payments"] = list_payments(conn, company_id)
    out["users"] = fetch_all(
        conn,
        """SELECT id, email, name, role, job_title, is_active, must_change_password, last_login_at, created_at
           FROM users WHERE company_id=? AND role IN ('admin','employee') ORDER BY role, name""",
        (company_id,),
    )
    out["customer_logins"] = fetch_one(
        conn, "SELECT COUNT(*) n FROM users WHERE company_id=? AND role='customer'", (company_id,))["n"]
    return out


def _blank(v) -> str | None:
    s = (v or "").strip() if isinstance(v, str) else v
    return s or None


def plan_list_price(plan: dict, billing_cycle: str) -> int:
    return int(plan["price_yearly"] if billing_cycle == "yearly" else plan["price_monthly"])


_PROFILE_KEYS = {
    "name": "company_name",
    "contact_phone": "company_phone",
    "contact_email": "company_email",
    "address": "company_address",
}


def _write_tenant_profile(db_path: str, fields: dict) -> None:
    settings = {dst: (fields[src] or "") for src, dst in _PROFILE_KEYS.items() if src in fields}
    if not settings:
        return
    path = resolve_db_path(db_path)
    if not os.path.exists(path):
        return
    tconn = sqlite3.connect(path)
    try:
        for key, val in settings.items():
            tconn.execute("INSERT OR REPLACE INTO company_settings(key, value) VALUES(?, ?)", (key, val))
        tconn.commit()
    finally:
        tconn.close()


def create_company(conn, *, name: str, slug: str | None = None, contact_name: str | None = None,
                   contact_email: str | None = None, contact_phone: str | None = None,
                   city: str | None = None, address: str | None = None, notes: str | None = None,
                   plan_id: int, billing_cycle: str = "monthly", amount: int | None = None,
                   trial_days: int = 14, grace_days: int = 7, subscription_notes: str | None = None,
                   db_path: str | None = None, seed_sample: bool = False,
                   record_opening_balance: bool = False, opening_cash: int | None = None,
                   opening_bank: int | None = None, opening_date: str | None = None) -> dict:
    from backend.db.seed import init_db

    name = (name or "").strip()
    if not name:
        raise ValueError("Company name is required")
    plan = fetch_one(conn, "SELECT * FROM plans WHERE id=?", (plan_id,))
    if not plan:
        raise ValueError("Choose a plan")
    if billing_cycle not in ("monthly", "yearly"):
        raise ValueError("Billing cycle must be monthly or yearly")
    contact_name = _blank(contact_name)
    contact_email = normalize_email(contact_email)
    contact_phone = normalize_phone(contact_phone)
    city = _blank(city)
    address = _blank(address)
    notes = _blank(notes)
    sub_notes = _blank(subscription_notes)
    base = slugify(slug or name)
    slug_final, n = base, 2
    while fetch_one(conn, "SELECT id FROM companies WHERE slug=?", (slug_final,)):
        slug_final = f"{base}-{n}"
        n += 1
    if db_path is None:
        os.makedirs(TENANTS_DIR, exist_ok=True)
        db_path = os.path.join(TENANTS_DIR, f"{slug_final}.db")
        if os.path.exists(db_path):
            raise ValueError("A database file for this company already exists")
    init_db(path=db_path, seed=seed_sample)
    _write_tenant_profile(db_path, {"name": name, "contact_phone": contact_phone,
                                   "contact_email": contact_email, "address": address})
    cur = conn.execute(
        """INSERT INTO companies(name, slug, db_path, contact_name, contact_email, contact_phone, city, address, notes)
           VALUES(?,?,?,?,?,?,?,?,?)""",
        (name, slug_final, _store_db_path(db_path), contact_name, contact_email, contact_phone, city, address, notes),
    )
    cid = cur.lastrowid
    today = date.today()
    price = plan_list_price(plan, billing_cycle)
    trial = max(int(trial_days or 0), 0)
    conn.execute(
        """INSERT INTO subscriptions(company_id, plan_id, billing_cycle, amount, is_trial, started_on,
                                     current_period_end, grace_days, notes)
           VALUES(?,?,?,?,?,?,?,?,?)""",
        (cid, plan_id, billing_cycle, price if amount is None else int(amount), int(trial > 0),
         today.isoformat(), (today + timedelta(days=trial)).isoformat(), int(grace_days), sub_notes),
    )
    audit(conn, "company.create", company_id=cid, target_type="company", target_id=cid,
          details={"name": name, "plan": plan["name"], "trial_days": trial, "amount": price if amount is None else int(amount)})
    if record_opening_balance:
        _seed_opening_balance(db_path, opening_cash or 0, opening_bank or 0, opening_date)
    return get_company(conn, cid)


def _seed_opening_balance(db_path: str, cash: int, bank: int, opening_date: str | None) -> None:
    if (cash or 0) <= 0 and (bank or 0) <= 0:
        return
    path = resolve_db_path(db_path)
    tconn = sqlite3.connect(path)
    tconn.row_factory = sqlite3.Row
    tconn.execute("PRAGMA foreign_keys = ON")
    try:
        from backend.auth.schema import ensure_tenant_schema
        ensure_tenant_schema(tconn)
        from backend.services import accounts as acc_svc
        acc_svc.set_current_balance(tconn, {
            "cash": int(cash or 0),
            "bank": int(bank or 0),
            "as_of": opening_date or date.today().isoformat(),
            "reason": "Recorded at company onboarding",
        }, allow_noop=True)
        tconn.commit()
    finally:
        tconn.close()


def update_company(conn, company_id: int, data: dict) -> dict:
    c = get_company(conn, company_id)
    if not c:
        raise LookupError("Company not found")
    incoming = {k: data[k] for k in ("name", "contact_name", "contact_email", "contact_phone",
                                     "city", "address", "notes", "status") if k in data}
    fields = {}
    for k, v in incoming.items():
        if k == "status":
            if v is None:
                continue
            fields[k] = v
        elif k == "contact_phone":
            fields[k] = normalize_phone(v)
        elif k == "contact_email":
            fields[k] = normalize_email(v)
        elif k == "name":
            name = (v or "").strip()
            if not name:
                raise ValueError("Company name is required")
            fields[k] = name
        else:
            fields[k] = _blank(v) if isinstance(v, str) or v is None else v
    if "status" in fields and fields["status"] not in ("active", "suspended"):
        raise ValueError("Invalid status")
    if fields:
        sets = ", ".join(f"{k}=?" for k in fields)
        conn.execute(f"UPDATE companies SET {sets}, updated_at=datetime('now') WHERE id=?", (*fields.values(), company_id))
        _write_tenant_profile(c["db_path"], fields)
    if fields.get("status") == "suspended" and c["status"] != "suspended":
        conn.execute(
            """UPDATE auth_sessions SET revoked_at=datetime('now')
               WHERE revoked_at IS NULL AND user_id IN
                 (SELECT id FROM users WHERE company_id=? AND role IN ('admin','employee'))""",
            (company_id,),
        )
    audit(conn, "company.update", company_id=company_id, target_type="company", target_id=company_id, details=fields)
    return get_company(conn, company_id)


def update_subscription(conn, company_id: int, data: dict) -> dict:
    sub = get_subscription(conn, company_id)
    if not sub:
        raise LookupError("Subscription not found")
    plan_id = int(data.get("plan_id") or sub["plan_id"])
    if not fetch_one(conn, "SELECT id FROM plans WHERE id=?", (plan_id,)):
        raise ValueError("Plan not found")
    cycle = data.get("billing_cycle") or sub["billing_cycle"]
    if cycle not in ("monthly", "yearly"):
        raise ValueError("Billing cycle must be monthly or yearly")
    end = data.get("current_period_end") or sub["current_period_end"]
    try:
        _d(end)
    except ValueError as e:
        raise ValueError("Invalid period end date") from e
    grace = int(data.get("grace_days") if data.get("grace_days") is not None else sub["grace_days"])
    if grace < 0 or grace > 90:
        raise ValueError("Grace days must be between 0 and 90")
    amount = int(data.get("amount") if data.get("amount") is not None else sub["amount"])
    conn.execute(
        """UPDATE subscriptions SET plan_id=?, billing_cycle=?, amount=?, current_period_end=?, grace_days=?,
                  is_trial=?, notes=?, updated_at=datetime('now') WHERE company_id=?""",
        (plan_id, cycle, amount, str(end)[:10], grace,
         int(data["is_trial"]) if data.get("is_trial") is not None else sub["is_trial"],
         data.get("notes", sub["notes"]), company_id),
    )
    audit(conn, "subscription.update", company_id=company_id, target_type="subscription", target_id=company_id,
          details={"plan_id": plan_id, "cycle": cycle, "amount": amount, "period_end": str(end)[:10], "grace": grace})
    return get_subscription(conn, company_id)


# ------------------------------------------------------------------ payments
def list_payments(conn, company_id: int | None = None, limit: int = 500) -> list[dict]:
    sql = """SELECT sp.*, c.name AS company_name, u.name AS recorded_by_name
             FROM subscription_payments sp
             JOIN companies c ON c.id=sp.company_id
             LEFT JOIN users u ON u.id=sp.recorded_by"""
    params: tuple = ()
    if company_id is not None:
        sql += " WHERE sp.company_id=?"
        params = (company_id,)
    return fetch_all(conn, sql + " ORDER BY sp.paid_on DESC, sp.id DESC LIMIT ?", (*params, limit))


def _next_receipt(conn) -> str:
    row = fetch_one(conn, "SELECT MAX(CAST(SUBSTR(receipt_no, 5) AS INTEGER)) n FROM subscription_payments")
    return f"SUB-{(row['n'] or 0) + 1:05d}"


def record_payment(conn, company_id: int, *, amount: int, paid_on: str, method: str, periods: int = 1,
                   reference: str | None = None, notes: str | None = None, recorded_by: int | None = None) -> dict:
    sub = get_subscription(conn, company_id)
    if not sub:
        raise LookupError("Subscription not found")
    amount = int(amount or 0)
    if amount <= 0:
        raise ValueError("Amount must be greater than zero")
    if method not in PAYMENT_METHODS:
        raise ValueError("Choose a payment method")
    periods = int(periods or 1)
    if not 1 <= periods <= 36:
        raise ValueError("Periods must be between 1 and 36")
    try:
        paid = _d(paid_on)
    except ValueError as e:
        raise ValueError("Invalid payment date") from e
    if paid > date.today() + timedelta(days=1):
        raise ValueError("Payment date cannot be in the future")
    end = _d(sub["current_period_end"])
    if sub["is_trial"]:
        # Paid period begins when the trial ends (or today, if the trial is already over).
        start = max(paid, end + timedelta(days=1))
    elif paid <= end + timedelta(days=sub["grace_days"] or 0):
        # Renewal on time or within grace: continue seamlessly from the current period.
        start = end + timedelta(days=1)
    else:
        # Lapsed: the new period starts on the payment date.
        start = paid
    months = periods * (12 if sub["billing_cycle"] == "yearly" else 1)
    new_end = add_months(start, months) - timedelta(days=1)
    receipt = _next_receipt(conn)
    cur = conn.execute(
        """INSERT INTO subscription_payments(receipt_no, company_id, amount, paid_on, method, reference,
                                             period_start, period_end, notes, recorded_by)
           VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (receipt, company_id, amount, paid.isoformat(), method, reference, start.isoformat(),
         new_end.isoformat(), notes, recorded_by),
    )
    conn.execute(
        "UPDATE subscriptions SET current_period_end=?, is_trial=0, updated_at=datetime('now') WHERE company_id=?",
        (new_end.isoformat(), company_id),
    )
    audit(conn, "payment.record", company_id=company_id, target_type="subscription_payment", target_id=cur.lastrowid,
          details={"receipt": receipt, "amount": amount, "period_end": new_end.isoformat()})
    return fetch_one(conn, "SELECT * FROM subscription_payments WHERE id=?", (cur.lastrowid,))


def void_payment(conn, payment_id: int, reason: str) -> dict:
    p = fetch_one(conn, "SELECT * FROM subscription_payments WHERE id=?", (payment_id,))
    if not p:
        raise LookupError("Payment not found")
    if p["voided_at"]:
        raise ValueError("Payment is already voided")
    if not (reason or "").strip():
        raise ValueError("Give a reason for voiding")
    latest = fetch_one(
        conn,
        """SELECT id FROM subscription_payments WHERE company_id=? AND voided_at IS NULL
           ORDER BY period_end DESC, id DESC LIMIT 1""",
        (p["company_id"],),
    )
    if not latest or latest["id"] != payment_id:
        raise ValueError("Only the most recent payment can be voided")
    conn.execute(
        "UPDATE subscription_payments SET voided_at=datetime('now'), void_reason=? WHERE id=?",
        (reason.strip(), payment_id),
    )
    rolled_back = (_d(p["period_start"]) - timedelta(days=1)).isoformat()
    conn.execute("UPDATE subscriptions SET current_period_end=?, updated_at=datetime('now') WHERE company_id=?",
                 (rolled_back, p["company_id"]))
    audit(conn, "payment.void", company_id=p["company_id"], target_type="subscription_payment", target_id=payment_id,
          details={"receipt": p["receipt_no"], "reason": reason, "period_end": rolled_back})
    return fetch_one(conn, "SELECT * FROM subscription_payments WHERE id=?", (payment_id,))


def overview(conn) -> dict:
    companies = list_companies(conn)
    today = date.today()
    month_start = today.replace(day=1).isoformat()
    mrr = 0
    for c in companies:
        if c["subscription"]["state"] in ("active", "grace") and c.get("amount"):
            mrr += c["amount"] // 12 if c["billing_cycle"] == "yearly" else c["amount"]
    by_state: dict[str, int] = {}
    for c in companies:
        by_state[c["subscription"]["state"]] = by_state.get(c["subscription"]["state"], 0) + 1
    collected = fetch_one(
        conn, "SELECT COALESCE(SUM(amount),0) v FROM subscription_payments WHERE voided_at IS NULL AND paid_on>=?",
        (month_start,))["v"]
    renewals = sorted(
        [c for c in companies if c["subscription"]["state"] in ("active", "trial", "grace")
         and c["subscription"].get("days_left", 99) <= 14],
        key=lambda c: c["subscription"].get("days_left", 0),
    )
    return {
        "companies": len(companies),
        "by_state": by_state,
        "mrr": mrr,
        "collected_this_month": collected,
        "renewals_due": [{"id": c["id"], "name": c["name"], "state": c["subscription"], "amount": c["amount"],
                          "billing_cycle": c["billing_cycle"]} for c in renewals],
        "recent_payments": list_payments(conn, limit=8),
    }


# ------------------------------------------------------------------ limits
def check_limit(conn, company_id: int, kind: str, current: int) -> None:
    sub = get_subscription(conn, company_id)
    if not sub:
        return
    limit = sub["max_employees"] if kind == "employees" else sub["max_projects"]
    if limit is not None and current >= limit:
        raise ValueError(
            f"Your {sub['plan_name']} plan allows {limit} {kind}. Ask your platform administrator to upgrade."
        )


# ------------------------------------------------------------------ bootstrap
def default_company_id(conn) -> int | None:
    slug = os.environ.get("ERP_DEFAULT_COMPANY")
    row = None
    if slug:
        row = fetch_one(conn, "SELECT id FROM companies WHERE slug=?", (slug,))
    if not row:
        row = fetch_one(conn, "SELECT id FROM companies WHERE status='active' ORDER BY id LIMIT 1")
    return row["id"] if row else None


def bootstrap_platform() -> None:
    """Create platform tables, register the legacy single-company database, upgrade every company DB."""
    from backend.database import platform_db
    from backend.db.seed import init_db
    from backend.saas.schema import ensure_platform_schema

    ensure_platform_schema()
    with platform_db() as conn:
        if not fetch_one(conn, "SELECT id FROM companies LIMIT 1"):
            _register_legacy_company(conn)
        companies = fetch_all(conn, "SELECT id, db_path FROM companies")
    for c in companies:
        path = resolve_db_path(c["db_path"])
        is_legacy = os.path.abspath(path) == os.path.abspath(DB_PATH)
        init_db(path=path, seed=is_legacy)


def _register_legacy_company(conn) -> None:
    from backend.db.seed import init_db

    init_db(path=DB_PATH, seed=True)
    legacy = sqlite3.connect(DB_PATH)
    legacy.row_factory = sqlite3.Row
    try:
        row = legacy.execute("SELECT value FROM company_settings WHERE key='company_name'").fetchone()
        name = row[0] if row and row[0] else "Haven Builders"
        has_users = legacy.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
        old_users = [dict(r) for r in legacy.execute("SELECT * FROM users")] if has_users else []
        cnic = {r["id"]: r["cnic"] for r in legacy.execute("SELECT id, cnic FROM customers")}
    finally:
        legacy.close()
    # Existing installs keep working without limits; the super admin can change the plan later.
    plan = fetch_one(conn, "SELECT * FROM plans WHERE code='enterprise'") or fetch_one(conn, "SELECT * FROM plans LIMIT 1")
    cur = conn.execute(
        "INSERT INTO companies(name, slug, db_path) VALUES(?,?,?)",
        (name, slugify(name.split()[0] if name else "company"), _store_db_path(DB_PATH)),
    )
    cid = cur.lastrowid
    today = date.today()
    conn.execute(
        """INSERT INTO subscriptions(company_id, plan_id, billing_cycle, amount, is_trial, started_on,
                                     current_period_end, grace_days, notes)
           VALUES(?,?,?,?,1,?,?,7,'Migrated from single-company install')""",
        (cid, plan["id"], "monthly", plan["price_monthly"], today.isoformat(),
         (today + timedelta(days=30)).isoformat()),
    )
    # Accounts created by the earlier single-company version move to the platform database.
    for u in old_users:
        role = u["role"]
        digits = None
        if role == "customer":
            digits = "".join(ch for ch in (cnic.get(u["customer_id"]) or "") if ch.isdigit()) or None
        conn.execute(
            """INSERT OR IGNORE INTO users(email, name, role, company_id, customer_id, cnic_digits, password_hash,
                                           is_active, must_change_password, last_login_at, password_changed_at,
                                           created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (u["email"], u["name"], role, None if role == "superadmin" else cid,
             u["customer_id"] if role == "customer" else None, digits, u["password_hash"], u["is_active"],
             u["must_change_password"], u["last_login_at"], u["password_changed_at"], u["created_at"]),
        )
    audit(conn, "company.migrate", company_id=cid, target_type="company", target_id=cid,
          details={"name": name, "migrated_users": len(old_users)})
