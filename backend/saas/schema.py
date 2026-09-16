"""Platform database: one row per company, their subscription, and every login."""
import os
import sqlite3

from backend.config import PLATFORM_DB_PATH

PLATFORM_SQL = """
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE COLLATE NOCASE,
    db_path TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','suspended')),
    contact_name TEXT,
    contact_email TEXT,
    contact_phone TEXT,
    city TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    price_monthly INTEGER NOT NULL DEFAULT 0,
    price_yearly INTEGER NOT NULL DEFAULT 0,
    max_employees INTEGER,          -- NULL = unlimited
    max_projects INTEGER,           -- NULL = unlimited
    description TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS subscriptions (
    company_id INTEGER PRIMARY KEY,
    plan_id INTEGER NOT NULL,
    billing_cycle TEXT NOT NULL DEFAULT 'monthly' CHECK (billing_cycle IN ('monthly','yearly')),
    amount INTEGER NOT NULL DEFAULT 0,       -- agreed price per cycle (PKR)
    is_trial INTEGER NOT NULL DEFAULT 0,
    started_on TEXT NOT NULL,
    current_period_end TEXT NOT NULL,
    grace_days INTEGER NOT NULL DEFAULT 7,
    notes TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
    FOREIGN KEY (plan_id) REFERENCES plans(id)
);

CREATE TABLE IF NOT EXISTS subscription_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_no TEXT NOT NULL UNIQUE,
    company_id INTEGER NOT NULL,
    amount INTEGER NOT NULL CHECK (amount > 0),
    paid_on TEXT NOT NULL,
    method TEXT NOT NULL,
    reference TEXT,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    notes TEXT,
    recorded_by INTEGER,
    voided_at TEXT,
    void_reason TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (company_id) REFERENCES companies(id)
);
CREATE INDEX IF NOT EXISTS idx_sub_payments_company ON subscription_payments(company_id, paid_on);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('superadmin','admin','employee','customer')),
    company_id INTEGER,
    customer_id INTEGER,            -- id inside the company's own database
    cnic_digits TEXT,               -- customers may sign in with CNIC
    job_title TEXT,
    password_hash TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    must_change_password INTEGER NOT NULL DEFAULT 1,
    all_projects INTEGER NOT NULL DEFAULT 1,   -- employees: 0 = only employee_projects
    last_login_at TEXT,
    password_changed_at TEXT,
    created_by INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (company_id) REFERENCES companies(id),
    CHECK ((role = 'superadmin') = (company_id IS NULL)),
    CHECK ((role = 'customer') = (customer_id IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_users_company ON users(company_id, role);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_company_customer ON users(company_id, customer_id) WHERE customer_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_users_cnic ON users(cnic_digits) WHERE cnic_digits IS NOT NULL;

CREATE TABLE IF NOT EXISTS employee_permissions (
    user_id INTEGER NOT NULL,
    module TEXT NOT NULL,
    can_view INTEGER NOT NULL DEFAULT 0,
    can_add INTEGER NOT NULL DEFAULT 0,
    can_edit INTEGER NOT NULL DEFAULT 0,
    can_delete INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, module),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS employee_projects (
    user_id INTEGER NOT NULL,
    project_id INTEGER NOT NULL,
    PRIMARY KEY (user_id, project_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    company_id INTEGER,             -- workspace; for a superadmin in support mode this is the company opened
    support_mode INTEGER NOT NULL DEFAULT 0,
    csrf_token TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL,
    ip TEXT,
    user_agent TEXT,
    revoked_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions(user_id);

CREATE TABLE IF NOT EXISTS login_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    identifier TEXT NOT NULL,
    ip TEXT,
    success INTEGER NOT NULL,
    attempted_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_login_attempts_ident ON login_attempts(identifier, attempted_at);
CREATE INDEX IF NOT EXISTS idx_login_attempts_ip ON login_attempts(ip, attempted_at);

CREATE TABLE IF NOT EXISTS platform_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    company_id INTEGER,
    action TEXT NOT NULL,
    target_type TEXT,
    target_id INTEGER,
    details TEXT,
    ip TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_platform_audit_company ON platform_audit(company_id, id);
"""

DEFAULT_PLANS = [
    # code, name, monthly, yearly, max_employees, max_projects, description, sort
    ("starter", "Starter", 15000, 150000, 3, 2, "Small builders — up to 2 projects and 3 employees.", 1),
    ("growth", "Growth", 35000, 350000, 15, 10, "Growing developers — up to 10 projects and 15 employees.", 2),
    ("enterprise", "Enterprise", 75000, 750000, None, None, "Unlimited projects and employees.", 3),
]


def ensure_platform_schema() -> None:
    os.makedirs(os.path.dirname(PLATFORM_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(PLATFORM_DB_PATH)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(PLATFORM_SQL)
        for row in DEFAULT_PLANS:
            conn.execute(
                """INSERT OR IGNORE INTO plans(code, name, price_monthly, price_yearly, max_employees,
                                               max_projects, description, sort_order)
                   VALUES(?,?,?,?,?,?,?,?)""",
                row,
            )
        conn.commit()
    finally:
        conn.close()
