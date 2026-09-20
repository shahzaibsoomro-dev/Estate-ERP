"""Additive per-company tables (documents, audit actor, public flag). Safe to run on every startup.

Logins, sessions and subscriptions live in the platform database (backend/saas/schema.py)."""
import sqlite3

TENANT_SQL = """
CREATE TABLE IF NOT EXISTS document_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE,
    name TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'general',
    description TEXT,
    body_html TEXT NOT NULL,
    requires_booking INTEGER NOT NULL DEFAULT 1,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_by INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS customer_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_no TEXT NOT NULL UNIQUE,
    customer_id INTEGER NOT NULL,
    booking_id INTEGER,
    template_id INTEGER,
    title TEXT NOT NULL,
    body_html TEXT NOT NULL,
    visible_to_customer INTEGER NOT NULL DEFAULT 1,
    created_by INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    revoked_at TEXT,
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    FOREIGN KEY (booking_id) REFERENCES bookings(id),
    FOREIGN KEY (template_id) REFERENCES document_templates(id)
);
CREATE INDEX IF NOT EXISTS idx_customer_documents_customer ON customer_documents(customer_id);

CREATE TABLE IF NOT EXISTS site_log_attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_log_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    mime TEXT,
    size INTEGER DEFAULT 0,
    kind TEXT NOT NULL DEFAULT 'file',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (site_log_id) REFERENCES site_logs(id)
);
CREATE INDEX IF NOT EXISTS idx_site_log_att_log ON site_log_attachments(site_log_id);
"""


def _has_column(conn: sqlite3.Connection, table: str, col: str) -> bool:
    return any(r[1] == col for r in conn.execute(f"PRAGMA table_info({table})"))


def ensure_tenant_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(TENANT_SQL)
    if not _has_column(conn, "audit_log", "user_id"):
        conn.execute("ALTER TABLE audit_log ADD COLUMN user_id INTEGER")
    if not _has_column(conn, "audit_log", "ip"):
        conn.execute("ALTER TABLE audit_log ADD COLUMN ip TEXT")
    if not _has_column(conn, "ledger_entries", "payment_method"):
        conn.execute("ALTER TABLE ledger_entries ADD COLUMN payment_method TEXT")
    if not _has_column(conn, "ledger_entries", "project_id"):
        conn.execute("ALTER TABLE ledger_entries ADD COLUMN project_id INTEGER")
    if not _has_column(conn, "projects", "is_public"):
        conn.execute("ALTER TABLE projects ADD COLUMN is_public INTEGER NOT NULL DEFAULT 1")
        # Hide leftovers from automated test runs on the public website.
        conn.execute(
            """UPDATE projects SET is_public=0
               WHERE name GLOB '*[0-9][0-9][0-9][0-9][0-9][0-9][0-9]*' OR name LIKE '%test%'"""
        )
    if not _has_column(conn, "projects", "project_type"):
        conn.execute("ALTER TABLE projects ADD COLUMN project_type TEXT NOT NULL DEFAULT 'building'")
    conn.execute(
        """UPDATE units SET unit_type='commercial'
           WHERE lower(unit_type) IN ('shop','office','showroom','warehouse','commercial')"""
    )
    conn.execute(
        """UPDATE units SET unit_type='residential'
           WHERE unit_type IS NULL OR lower(unit_type) NOT IN ('residential','commercial')"""
    )
    conn.execute("UPDATE units SET residential_type=NULL WHERE lower(unit_type)='commercial'")
    _ensure_cols(conn)
    from backend.documents.defaults import seed_default_templates, upgrade_default_templates
    seed_default_templates(conn)
    upgrade_default_templates(conn)


def _ensure_cols(conn: sqlite3.Connection) -> None:
    cols = {
        "purchase_orders": [
            ("pack_qty", "REAL"),
            ("pack_size", "REAL DEFAULT 1"),
            ("pack_unit", "TEXT"),
            ("total_units", "REAL"),
            ("cancel_fee_pct", "REAL"),
            ("cancel_fee_amount", "INTEGER DEFAULT 0"),
            ("cancel_refund_amount", "INTEGER DEFAULT 0"),
            ("cancelled_at", "TEXT"),
            ("cancel_reason", "TEXT"),
        ],
        "contractors": [
            ("company_name", "TEXT"),
            ("father_name", "TEXT"),
            ("email", "TEXT"),
            ("address", "TEXT"),
            ("city", "TEXT"),
            ("pec_no", "TEXT"),
            ("bank_name", "TEXT"),
            ("account_title", "TEXT"),
            ("account_no", "TEXT"),
            ("emergency_contact", "TEXT"),
        ],
        "site_logs": [
            ("reporter", "TEXT"),
            ("time_from", "TEXT"),
            ("time_to", "TEXT"),
            ("hours_worked", "REAL"),
            ("extra_expenses", "INTEGER DEFAULT 0"),
            ("expense_notes", "TEXT"),
            ("notes", "TEXT"),
            ("workforce_notes", "TEXT"),
            ("materials_json", "TEXT"),
        ],
    }
    for table, pairs in cols.items():
        for col, spec in pairs:
            if not _has_column(conn, table, col):
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {spec}")
