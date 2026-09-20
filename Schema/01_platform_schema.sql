-- ============================================================================
-- Haven Builders ERP — PostgreSQL platform schema
-- ============================================================================
-- Source of truth today: backend/saas/schema.py (SQLite, db/platform.db)
--
-- This holds data that is shared across ALL tenants: companies, plans,
-- subscriptions/billing, logins/sessions, and platform-level audit.
-- It lives in its own Postgres schema ("platform") in the same database
-- as every tenant schema (see 02_tenant_schema.sql).
--
-- Run once per database, before any tenant schema is created:
--   psql "$DATABASE_URL" -f Schema/00_extensions.sql
--   psql "$DATABASE_URL" -f Schema/01_platform_schema.sql
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS platform;
SET search_path TO platform;

-- ----------------------------------------------------------------------------
-- companies — one row per real-estate company (tenant)
-- ----------------------------------------------------------------------------
CREATE TABLE companies (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name            TEXT NOT NULL,
    slug            CITEXT NOT NULL UNIQUE,          -- was: TEXT UNIQUE COLLATE NOCASE
    schema_name     TEXT NOT NULL UNIQUE,            -- was: db_path (file path) -> now a Postgres schema name
    status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','suspended')),
    contact_name    TEXT,
    contact_email   TEXT,
    contact_phone   TEXT,
    city            TEXT,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ----------------------------------------------------------------------------
-- plans — subscription tiers
-- ----------------------------------------------------------------------------
CREATE TABLE plans (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code            TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    price_monthly   NUMERIC(14,2) NOT NULL DEFAULT 0,   -- was: INTEGER (PKR, whole rupees)
    price_yearly    NUMERIC(14,2) NOT NULL DEFAULT 0,
    max_employees   INTEGER,          -- NULL = unlimited
    max_projects    INTEGER,          -- NULL = unlimited
    description     TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order      INTEGER NOT NULL DEFAULT 0
);

-- ----------------------------------------------------------------------------
-- subscriptions — one active subscription per company
-- ----------------------------------------------------------------------------
CREATE TABLE subscriptions (
    company_id          BIGINT PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
    plan_id             BIGINT NOT NULL REFERENCES plans(id),
    billing_cycle       TEXT NOT NULL DEFAULT 'monthly' CHECK (billing_cycle IN ('monthly','yearly')),
    amount              NUMERIC(14,2) NOT NULL DEFAULT 0,   -- agreed price per cycle (PKR)
    is_trial            BOOLEAN NOT NULL DEFAULT FALSE,
    started_on          DATE NOT NULL,
    current_period_end  DATE NOT NULL,
    grace_days          INTEGER NOT NULL DEFAULT 7,
    notes               TEXT,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ----------------------------------------------------------------------------
-- subscription_payments — billing history (bank transfer / cash / cheque / …)
-- ----------------------------------------------------------------------------
CREATE TABLE subscription_payments (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    receipt_no      TEXT NOT NULL UNIQUE,
    company_id      BIGINT NOT NULL REFERENCES companies(id),
    amount          NUMERIC(14,2) NOT NULL CHECK (amount > 0),
    paid_on         DATE NOT NULL,
    method          TEXT NOT NULL,
    reference       TEXT,
    period_start    DATE NOT NULL,
    period_end      DATE NOT NULL,
    notes           TEXT,
    recorded_by     BIGINT,
    voided_at       TIMESTAMPTZ,
    void_reason     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_sub_payments_company ON subscription_payments(company_id, paid_on);

-- ----------------------------------------------------------------------------
-- users — every login: superadmin / admin / employee / customer
-- ----------------------------------------------------------------------------
CREATE TABLE users (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email               CITEXT NOT NULL UNIQUE,          -- was: TEXT UNIQUE COLLATE NOCASE
    name                TEXT NOT NULL,
    role                TEXT NOT NULL CHECK (role IN ('superadmin','admin','employee','customer')),
    company_id          BIGINT REFERENCES companies(id),
    customer_id         BIGINT,           -- id inside the company's own tenant schema (no FK: cross-schema)
    cnic_digits         TEXT,             -- customers may sign in with CNIC
    job_title           TEXT,
    password_hash       TEXT NOT NULL,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    must_change_password BOOLEAN NOT NULL DEFAULT TRUE,
    all_projects        BOOLEAN NOT NULL DEFAULT TRUE,   -- employees: FALSE = only employee_projects
    last_login_at       TIMESTAMPTZ,
    password_changed_at TIMESTAMPTZ,
    created_by          BIGINT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((role = 'superadmin') = (company_id IS NULL)),
    CHECK ((role = 'customer') = (customer_id IS NOT NULL))
);
CREATE INDEX idx_users_company ON users(company_id, role);
CREATE UNIQUE INDEX idx_users_company_customer ON users(company_id, customer_id) WHERE customer_id IS NOT NULL;
CREATE INDEX idx_users_cnic ON users(cnic_digits) WHERE cnic_digits IS NOT NULL;

-- ----------------------------------------------------------------------------
-- employee_permissions — per-module CRUD flags for employee accounts
-- ----------------------------------------------------------------------------
CREATE TABLE employee_permissions (
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    module      TEXT NOT NULL,
    can_view    BOOLEAN NOT NULL DEFAULT FALSE,
    can_add     BOOLEAN NOT NULL DEFAULT FALSE,
    can_edit    BOOLEAN NOT NULL DEFAULT FALSE,
    can_delete  BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (user_id, module)
);

-- ----------------------------------------------------------------------------
-- employee_projects — project scoping for employees with all_projects = FALSE
-- ----------------------------------------------------------------------------
CREATE TABLE employee_projects (
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id  BIGINT NOT NULL,   -- id inside the company's tenant schema (no FK: cross-schema)
    PRIMARY KEY (user_id, project_id)
);

-- ----------------------------------------------------------------------------
-- auth_sessions — server-side session store
-- ----------------------------------------------------------------------------
CREATE TABLE auth_sessions (
    token_hash      TEXT PRIMARY KEY,
    user_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    company_id      BIGINT,     -- workspace; for a superadmin in support mode, the company opened
    support_mode    BOOLEAN NOT NULL DEFAULT FALSE,
    csrf_token      TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ NOT NULL,
    ip              INET,               -- was: TEXT
    user_agent      TEXT,
    revoked_at      TIMESTAMPTZ
);
CREATE INDEX idx_auth_sessions_user ON auth_sessions(user_id);
CREATE INDEX idx_auth_sessions_expiry ON auth_sessions(expires_at) WHERE revoked_at IS NULL;

-- ----------------------------------------------------------------------------
-- login_attempts — throttling (5 / account, 20 / IP per 15 min)
-- ----------------------------------------------------------------------------
CREATE TABLE login_attempts (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    identifier      TEXT NOT NULL,
    ip              INET,
    success         BOOLEAN NOT NULL,
    attempted_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_login_attempts_ident ON login_attempts(identifier, attempted_at);
CREATE INDEX idx_login_attempts_ip ON login_attempts(ip, attempted_at);

-- ----------------------------------------------------------------------------
-- platform_audit — sign-ins, access changes, payments, support sessions
-- ----------------------------------------------------------------------------
CREATE TABLE platform_audit (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         BIGINT,
    company_id      BIGINT,
    action          TEXT NOT NULL,
    target_type     TEXT,
    target_id       BIGINT,
    details          JSONB,          -- was: TEXT (free-form JSON string)
    ip              INET,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_platform_audit_company ON platform_audit(company_id, id);

-- ----------------------------------------------------------------------------
-- Seed default plans
-- ----------------------------------------------------------------------------
INSERT INTO plans (code, name, price_monthly, price_yearly, max_employees, max_projects, description, sort_order)
VALUES
    ('starter',    'Starter',    15000, 150000, 3,    2,    'Small builders — up to 2 projects and 3 employees.', 1),
    ('growth',     'Growth',     35000, 350000, 15,   10,   'Growing developers — up to 10 projects and 15 employees.', 2),
    ('enterprise', 'Enterprise', 75000, 750000, NULL, NULL, 'Unlimited projects and employees.', 3)
ON CONFLICT (code) DO NOTHING;

RESET search_path;
