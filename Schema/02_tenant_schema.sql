-- ============================================================================
-- Haven Builders ERP — PostgreSQL tenant schema (template)
-- ============================================================================
-- Source of truth today: backend/db/schema.sql + backend/auth/schema.py
--                         (SQLite, one db/tenants/<slug>.db file per company)
--
-- This is the per-tenant business schema: projects, units, customers,
-- bookings, installments, payments, procurement, agents, investors,
-- partners, budgets, site logs, holds, documents, audit.
--
-- Every tenant gets its OWN Postgres schema (not its own database, not a
-- shared table with tenant_id) so isolation matches what the app already
-- assumes today. To provision a new company:
--
--   CREATE SCHEMA tenant_acme;
--   SET search_path TO tenant_acme;
--   \i Schema/02_tenant_schema.sql
--   RESET search_path;
--
-- and record ('acme', 'tenant_acme') in platform.companies(slug, schema_name).
-- ============================================================================

-- NOTE: no CREATE SCHEMA / SET search_path here on purpose — the provisioning
-- script controls which schema this runs into (see header above).

-- ----------------------------------------------------------------------------
-- schema_meta / company_settings — key/value config
-- ----------------------------------------------------------------------------
CREATE TABLE schema_meta (
    key     TEXT PRIMARY KEY,
    value   TEXT NOT NULL
);

CREATE TABLE company_settings (
    key     TEXT PRIMARY KEY,
    value   TEXT NOT NULL
);

-- ----------------------------------------------------------------------------
-- projects — buildings / phases
-- ----------------------------------------------------------------------------
CREATE TABLE projects (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name                TEXT NOT NULL,
    location            TEXT,
    description         TEXT,
    area                TEXT,
    city                TEXT,
    start_date          DATE,
    expected_end_date   DATE,
    status              TEXT DEFAULT 'under_construction'
                        CHECK (status IN ('planning','under_construction','completed')),
    current_progress    INTEGER DEFAULT 0 CHECK (current_progress BETWEEN 0 AND 100),
    number_of_floors    INTEGER DEFAULT 0,
    number_of_units     INTEGER DEFAULT 0,
    project_attributes  JSONB DEFAULT '[]'::jsonb,   -- was: TEXT DEFAULT '[]'
    total_area_ghaz     NUMERIC(14,3),
    estimated_cost      NUMERIC(16,2),
    is_public           BOOLEAN NOT NULL DEFAULT TRUE   -- added at runtime today (auth/schema.py)
);

-- ----------------------------------------------------------------------------
-- customers — buyers
-- ----------------------------------------------------------------------------
CREATE TABLE customers (
    id                          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name                        TEXT NOT NULL,
    father_name                 TEXT,
    description                 TEXT,
    residential_address         TEXT,
    cnic                        TEXT UNIQUE,
    contact_number              TEXT,
    emergency_contact_number    TEXT,
    email                       TEXT,
    nok_name                    TEXT,
    nok_relationship            TEXT,
    nok_phone                   TEXT,
    nok_cnic                    TEXT,
    nok_address                 TEXT,
    created_at                  DATE DEFAULT CURRENT_DATE
);

-- ----------------------------------------------------------------------------
-- agents — brokers
-- ----------------------------------------------------------------------------
CREATE TABLE agents (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name                TEXT NOT NULL,
    description         TEXT,
    contact             TEXT,
    category            TEXT,
    default_rate_pct    NUMERIC(6,3) DEFAULT 2.0,
    bonus_budget        NUMERIC(14,2) DEFAULT 0,
    status              TEXT DEFAULT 'active'
);

-- ----------------------------------------------------------------------------
-- units — flats / shops
-- ----------------------------------------------------------------------------
CREATE TABLE units (
    id                          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id                  BIGINT NOT NULL REFERENCES projects(id),
    unit_no                     TEXT NOT NULL,
    description                 TEXT,
    unit_type                   TEXT DEFAULT 'Flat',
    residential_type            TEXT,
    floor_number                INTEGER DEFAULT 1,
    area_ghaz                   NUMERIC(14,3),
    block_tower                 TEXT,
    bedrooms                    INTEGER,
    bathrooms                   INTEGER,
    status                      TEXT DEFAULT 'available'
                                CHECK (status IN ('available','hold','sold','booked','possession_delivered','blocked')),
    base_sale_price             NUMERIC(16,2),
    final_sold_price            NUMERIC(16,2),
    booking_amount_required     NUMERIC(16,2),
    furnishing_status           TEXT,
    unit_attributes             JSONB DEFAULT '[]'::jsonb,   -- was: TEXT DEFAULT '[]'
    additional_requirements     TEXT,
    possession_date             DATE,
    hold_customer_id            BIGINT REFERENCES customers(id),
    hold_until                  DATE,
    hold_notes                  TEXT,
    UNIQUE (project_id, unit_no)
);

-- ----------------------------------------------------------------------------
-- bookings — unit sale
-- ----------------------------------------------------------------------------
CREATE TABLE bookings (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    booking_no          TEXT UNIQUE NOT NULL,
    customer_id         BIGINT NOT NULL REFERENCES customers(id),
    unit_id             BIGINT NOT NULL REFERENCES units(id),
    project_id          BIGINT NOT NULL REFERENCES projects(id),
    agent_id            BIGINT REFERENCES agents(id),
    booking_date        DATE NOT NULL,
    base_sale_price     NUMERIC(16,2) NOT NULL,
    final_sale_price    NUMERIC(16,2) NOT NULL,
    booking_amount      NUMERIC(16,2) NOT NULL,
    possession_date     DATE,
    status              TEXT DEFAULT 'active' CHECK (status IN ('active','completed','cancelled')),
    payment_mode        TEXT DEFAULT 'Cheque',
    notes               TEXT,
    plan_source         TEXT DEFAULT 'custom',
    template_id         BIGINT,   -- references project_installment_templates(id), added below via ALTER (fwd ref)
    template_revision   INTEGER,
    template_name       TEXT
);

-- ----------------------------------------------------------------------------
-- installments — payment schedule
-- ----------------------------------------------------------------------------
CREATE TABLE installments (
    id                          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    booking_id                  BIGINT NOT NULL REFERENCES bookings(id),
    customer_id                 BIGINT NOT NULL REFERENCES customers(id),
    unit_id                     BIGINT NOT NULL REFERENCES units(id),
    installment_no              INTEGER NOT NULL,
    due_date                    DATE NOT NULL,
    amount                      NUMERIC(16,2) NOT NULL,
    paid_amount                 NUMERIC(16,2) DEFAULT 0,
    remaining_amount            NUMERIC(16,2) NOT NULL,
    type                        TEXT DEFAULT 'Monthly' CHECK (type IN ('Booking','Monthly','Quarterly','Possession')),
    notes                       TEXT,
    status                      TEXT DEFAULT 'pending'
                                CHECK (status IN ('scheduled','pending','partial','paid','overdue','cancelled')),
    trigger_kind                TEXT DEFAULT 'time',
    trigger_progress            INTEGER,
    forecast_due_date           DATE,
    activated_at                TIMESTAMPTZ,
    trigger_label                TEXT,
    template_rule_id            BIGINT,   -- references project_installment_template_rules(id), fwd ref
    due_days_after_trigger      INTEGER DEFAULT 0
);

-- ----------------------------------------------------------------------------
-- payments — money received
-- ----------------------------------------------------------------------------
CREATE TABLE payments (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id         BIGINT NOT NULL REFERENCES customers(id),
    booking_id          BIGINT NOT NULL REFERENCES bookings(id),
    installment_id      BIGINT REFERENCES installments(id),
    amount              NUMERIC(16,2) NOT NULL,
    payment_date        DATE NOT NULL,
    payment_method      TEXT DEFAULT 'Cash',
    bank                TEXT,
    reference_number    TEXT,
    received_by         TEXT DEFAULT 'Admin',
    notes               TEXT
);

-- ----------------------------------------------------------------------------
-- receipts
-- ----------------------------------------------------------------------------
CREATE TABLE receipts (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payment_id      BIGINT NOT NULL UNIQUE REFERENCES payments(id),
    receipt_no      TEXT UNIQUE NOT NULL,
    issued_at       TIMESTAMPTZ DEFAULT now()
);

-- ----------------------------------------------------------------------------
-- booking_cancellations
-- ----------------------------------------------------------------------------
CREATE TABLE booking_cancellations (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    booking_id      BIGINT NOT NULL REFERENCES bookings(id),
    cancelled_at    TIMESTAMPTZ DEFAULT now(),
    reason          TEXT,
    total_paid      NUMERIC(16,2) NOT NULL,
    forfeit_amount  NUMERIC(16,2) NOT NULL,
    refund_amount   NUMERIC(16,2) NOT NULL,
    forfeit_pct     NUMERIC(6,3) NOT NULL
);

-- ----------------------------------------------------------------------------
-- booking_transfers
-- ----------------------------------------------------------------------------
CREATE TABLE booking_transfers (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    booking_id          BIGINT NOT NULL REFERENCES bookings(id),
    from_customer_id    BIGINT NOT NULL REFERENCES customers(id),
    to_customer_id      BIGINT NOT NULL REFERENCES customers(id),
    transfer_date       DATE NOT NULL,
    transfer_fee        NUMERIC(16,2) DEFAULT 0,
    notes               TEXT
);

-- ----------------------------------------------------------------------------
-- vendors — suppliers
-- ----------------------------------------------------------------------------
CREATE TABLE vendors (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT,
    contact         TEXT,
    category        TEXT,
    ntn             TEXT,
    status          TEXT DEFAULT 'active'
);

-- ----------------------------------------------------------------------------
-- budget_categories / project_budget_lines
-- ----------------------------------------------------------------------------
CREATE TABLE budget_categories (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    sort_order  INTEGER DEFAULT 0
);

CREATE TABLE project_budget_lines (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id      BIGINT NOT NULL REFERENCES projects(id),
    category_id     BIGINT NOT NULL REFERENCES budget_categories(id),
    planned_amount  NUMERIC(16,2) NOT NULL,
    revision_no     INTEGER DEFAULT 1,
    is_active       BOOLEAN DEFAULT TRUE,
    notes           TEXT
);

-- ----------------------------------------------------------------------------
-- purchase_orders / vendor_payments — procurement
-- ----------------------------------------------------------------------------
CREATE TABLE purchase_orders (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    po_no                   TEXT UNIQUE NOT NULL,
    vendor_id               BIGINT NOT NULL REFERENCES vendors(id),
    project_id              BIGINT NOT NULL REFERENCES projects(id),
    budget_category_id      BIGINT REFERENCES budget_categories(id),
    category                TEXT,
    material                TEXT NOT NULL,
    quantity                TEXT,
    unit_cost               NUMERIC(16,2),
    total                   NUMERIC(16,2) NOT NULL,
    order_date              DATE NOT NULL,
    expected_delivery_date  DATE,
    status                  TEXT DEFAULT 'ordered' CHECK (status IN ('ordered','cancelled','delivered','closed')),
    grn_status              TEXT DEFAULT 'pending',
    site                    TEXT,
    notes                   TEXT
);

CREATE TABLE vendor_payments (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vendor_id           BIGINT NOT NULL REFERENCES vendors(id),
    purchase_order_id   BIGINT REFERENCES purchase_orders(id),
    amount              NUMERIC(16,2) NOT NULL,
    payment_date        DATE NOT NULL,
    payment_method      TEXT DEFAULT 'Bank Transfer',
    reference_number    TEXT,
    notes               TEXT
);

-- ----------------------------------------------------------------------------
-- agent_commissions / agent_commission_payments / agent_bonuses
-- ----------------------------------------------------------------------------
CREATE TABLE agent_commissions (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    booking_id          BIGINT NOT NULL UNIQUE REFERENCES bookings(id),
    agent_id            BIGINT NOT NULL REFERENCES agents(id),
    rate_pct            NUMERIC(6,3) NOT NULL,
    commission_amount   NUMERIC(16,2) NOT NULL,
    paid_amount         NUMERIC(16,2) DEFAULT 0,
    status              TEXT DEFAULT 'earned'
);

CREATE TABLE agent_commission_payments (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    commission_id   BIGINT NOT NULL REFERENCES agent_commissions(id),
    amount          NUMERIC(16,2) NOT NULL,
    payment_date    DATE NOT NULL,
    notes           TEXT
);

CREATE TABLE agent_bonuses (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    agent_id    BIGINT NOT NULL REFERENCES agents(id),
    amount      NUMERIC(16,2) NOT NULL,
    bonus_date  DATE NOT NULL,
    reason      TEXT,
    notes       TEXT,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- ----------------------------------------------------------------------------
-- investors / investor_agreements / contributions / distributions
-- ----------------------------------------------------------------------------
CREATE TABLE investors (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name            TEXT NOT NULL,
    cnic            TEXT,
    mobile_number   TEXT,
    email           TEXT,
    description     TEXT,
    status          TEXT DEFAULT 'active'
);

CREATE TABLE investor_agreements (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    investor_id             BIGINT NOT NULL REFERENCES investors(id),
    project_id              BIGINT REFERENCES projects(id),
    investor_type           TEXT NOT NULL CHECK (investor_type IN ('Monthly Return','Profit Sharing')),
    investment_amount       NUMERIC(16,2) NOT NULL,
    investment_date         DATE NOT NULL,
    monthly_return_pct      NUMERIC(6,3),
    profit_share_pct        NUMERIC(6,3),
    returns_start_date      DATE,
    catch_up_policy         TEXT DEFAULT 'lump_sum',
    catch_up_months         INTEGER,
    profit_share_basis      TEXT,
    status                  TEXT DEFAULT 'active' CHECK (status IN ('active','completed','withdrawn'))
);

CREATE TABLE investor_contributions (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    agreement_id        BIGINT NOT NULL REFERENCES investor_agreements(id),
    amount              NUMERIC(16,2) NOT NULL,
    contribution_date   DATE NOT NULL,
    notes               TEXT
);

CREATE TABLE investor_distributions (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    agreement_id        BIGINT NOT NULL REFERENCES investor_agreements(id),
    amount              NUMERIC(16,2) NOT NULL,
    distribution_date   DATE NOT NULL,
    notes               TEXT
);

-- ----------------------------------------------------------------------------
-- partners / partner_agreements / contributions / distributions
-- (mirrors investors — internal/founder capital vs external investors)
-- ----------------------------------------------------------------------------
CREATE TABLE partners (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name            TEXT NOT NULL,
    cnic            TEXT,
    mobile_number   TEXT,
    email           TEXT,
    description     TEXT,
    status          TEXT DEFAULT 'active'
);

CREATE TABLE partner_agreements (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    partner_id          BIGINT NOT NULL REFERENCES partners(id),
    project_id          BIGINT REFERENCES projects(id),
    partner_type        TEXT NOT NULL,
    investment_amount   NUMERIC(16,2) NOT NULL,
    investment_date     DATE NOT NULL,
    monthly_return_pct  NUMERIC(6,3),
    profit_share_pct    NUMERIC(6,3),
    returns_start_date  DATE,
    catch_up_policy     TEXT DEFAULT 'lump_sum',
    catch_up_months     INTEGER,
    profit_share_basis  TEXT,
    status              TEXT DEFAULT 'active'
);

CREATE TABLE partner_contributions (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    agreement_id        BIGINT NOT NULL REFERENCES partner_agreements(id),
    amount              NUMERIC(16,2) NOT NULL,
    contribution_date   DATE NOT NULL,
    notes               TEXT
);

CREATE TABLE partner_distributions (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    agreement_id        BIGINT NOT NULL REFERENCES partner_agreements(id),
    amount              NUMERIC(16,2) NOT NULL,
    distribution_date   DATE NOT NULL,
    notes               TEXT
);

-- ----------------------------------------------------------------------------
-- audit_log — per-tenant activity trail
-- ----------------------------------------------------------------------------
CREATE TABLE audit_log (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entity_type     TEXT NOT NULL,
    entity_id       BIGINT,
    action          TEXT NOT NULL,
    details         JSONB,      -- was: TEXT
    created_at      TIMESTAMPTZ DEFAULT now(),
    user_id         BIGINT,     -- added at runtime today (auth/schema.py)
    ip              INET        -- added at runtime today (auth/schema.py)
);

-- ----------------------------------------------------------------------------
-- ledger_entries — simple GL
-- ----------------------------------------------------------------------------
CREATE TABLE ledger_entries (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entry_date      DATE NOT NULL,
    narration       TEXT NOT NULL,
    amount          NUMERIC(16,2) NOT NULL,
    direction       TEXT NOT NULL CHECK (direction IN ('in','out')),
    category        TEXT,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    payment_method  TEXT,       -- added at runtime today (auth/schema.py)
    project_id      BIGINT REFERENCES projects(id)   -- added at runtime today (auth/schema.py)
);

-- ----------------------------------------------------------------------------
-- site_logs — daily site diary
-- ----------------------------------------------------------------------------
CREATE TABLE site_logs (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id          BIGINT NOT NULL REFERENCES projects(id),
    log_date            DATE NOT NULL,
    engineer            TEXT NOT NULL,
    workers_skilled     INTEGER DEFAULT 0,
    workers_unskilled   INTEGER DEFAULT 0,
    material_used       TEXT,
    work_done           TEXT NOT NULL,
    created_at          TIMESTAMPTZ DEFAULT now()
);

-- ----------------------------------------------------------------------------
-- unit_holds / hold_transactions / hold_receipts / hold_token_applications
-- ----------------------------------------------------------------------------
CREATE TABLE unit_holds (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    unit_id                 BIGINT NOT NULL REFERENCES units(id),
    customer_id             BIGINT REFERENCES customers(id),
    hold_until              DATE,
    notes                   TEXT,
    status                  TEXT DEFAULT 'active',
    token_amount            NUMERIC(16,2) DEFAULT 0,
    held_at                 DATE DEFAULT CURRENT_DATE,
    released_at             TIMESTAMPTZ,
    release_reason          TEXT,
    converted_booking_id    BIGINT REFERENCES bookings(id),
    created_at              TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE hold_transactions (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    hold_id             BIGINT NOT NULL REFERENCES unit_holds(id),
    direction           TEXT NOT NULL CHECK (direction IN ('in','out','refund')),
    amount              NUMERIC(16,2) NOT NULL,
    txn_date            DATE NOT NULL,
    payment_method      TEXT DEFAULT 'Cash',
    bank                TEXT,
    reference_number    TEXT,
    received_by         TEXT DEFAULT 'Admin',
    notes               TEXT,
    voucher_no          TEXT,
    created_at          TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE hold_receipts (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    hold_id                 BIGINT NOT NULL REFERENCES unit_holds(id),
    receipt_no              TEXT UNIQUE NOT NULL,
    acknowledged_amount     NUMERIC(16,2) NOT NULL DEFAULT 0,
    transaction_id          BIGINT REFERENCES hold_transactions(id),
    issued_at               TIMESTAMPTZ DEFAULT now(),
    notes                   TEXT
);

CREATE TABLE hold_token_applications (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    hold_id         BIGINT NOT NULL REFERENCES unit_holds(id),
    booking_id      BIGINT NOT NULL REFERENCES bookings(id),
    payment_id      BIGINT NOT NULL REFERENCES payments(id),
    amount          NUMERIC(16,2) NOT NULL,
    applied_at      TIMESTAMPTZ DEFAULT now()
);

-- ----------------------------------------------------------------------------
-- project_installment_templates / _rules — reusable payment plan blueprints
-- ----------------------------------------------------------------------------
CREATE TABLE project_installment_templates (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id              BIGINT NOT NULL REFERENCES projects(id),
    name                    TEXT NOT NULL,
    default_booking_bps     INTEGER DEFAULT 1000,   -- basis points (1000 = 10%)
    revision                INTEGER DEFAULT 1,
    is_active               BOOLEAN DEFAULT TRUE,
    created_at              TIMESTAMPTZ DEFAULT now(),
    updated_at              TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE project_installment_template_rules (
    id                          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    template_id                 BIGINT NOT NULL REFERENCES project_installment_templates(id),
    sort_order                  INTEGER NOT NULL,
    label                       TEXT NOT NULL,
    trigger_kind                TEXT NOT NULL DEFAULT 'construction',
    amount_bps                  INTEGER NOT NULL,
    installment_count           INTEGER DEFAULT 1,
    start_offset_months         INTEGER DEFAULT 0,
    interval_months             INTEGER DEFAULT 1,
    milestone_progress          INTEGER,
    forecast_due_date           DATE,
    due_days_after_trigger      INTEGER DEFAULT 0,
    notes                       TEXT
);

-- Forward references from bookings/installments into the template tables
-- (tables above didn't exist yet when bookings/installments were created).
ALTER TABLE bookings
    ADD CONSTRAINT fk_bookings_template FOREIGN KEY (template_id) REFERENCES project_installment_templates(id);
ALTER TABLE installments
    ADD CONSTRAINT fk_installments_template_rule FOREIGN KEY (template_rule_id) REFERENCES project_installment_template_rules(id);

-- ----------------------------------------------------------------------------
-- contractors / contractor_assignments / contractor_payments
-- ----------------------------------------------------------------------------
CREATE TABLE contractors (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        TEXT NOT NULL,
    cnic        TEXT,
    contact     TEXT,
    ntn         TEXT,
    specialty   TEXT,
    description TEXT,
    status      TEXT DEFAULT 'active'
);

CREATE TABLE contractor_assignments (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    contractor_id       BIGINT NOT NULL REFERENCES contractors(id),
    project_id          BIGINT NOT NULL REFERENCES projects(id),
    role                TEXT,
    contract_amount     NUMERIC(16,2) DEFAULT 0,
    start_date          DATE,
    end_date            DATE,
    status              TEXT DEFAULT 'active',
    notes               TEXT
);

CREATE TABLE contractor_payments (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    contractor_id       BIGINT NOT NULL REFERENCES contractors(id),
    assignment_id       BIGINT REFERENCES contractor_assignments(id),
    project_id          BIGINT REFERENCES projects(id),
    amount              NUMERIC(16,2) NOT NULL,
    payment_date        DATE NOT NULL,
    payment_method      TEXT DEFAULT 'Bank Transfer',
    reference_number    TEXT,
    notes               TEXT
);

-- ----------------------------------------------------------------------------
-- inventory_items / inventory_movements
-- ----------------------------------------------------------------------------
CREATE TABLE inventory_items (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku         TEXT,
    name        TEXT NOT NULL,
    unit        TEXT DEFAULT 'pcs',
    category    TEXT,
    project_id  BIGINT REFERENCES projects(id),
    min_stock   NUMERIC(14,3) DEFAULT 0,
    notes       TEXT,
    status      TEXT DEFAULT 'active'
);

CREATE TABLE inventory_movements (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    item_id         BIGINT NOT NULL REFERENCES inventory_items(id),
    project_id      BIGINT REFERENCES projects(id),
    direction       TEXT NOT NULL CHECK (direction IN ('in','out')),
    quantity        NUMERIC(14,3) NOT NULL,
    unit_cost       NUMERIC(16,2) DEFAULT 0,
    reference_type  TEXT,
    reference_id    BIGINT,
    movement_date   DATE NOT NULL,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- ----------------------------------------------------------------------------
-- possession_checklist_templates / _template_items / possession_checklists / _responses
-- ----------------------------------------------------------------------------
CREATE TABLE possession_checklist_templates (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        TEXT NOT NULL,
    is_default  BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE possession_checklist_template_items (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    template_id     BIGINT NOT NULL REFERENCES possession_checklist_templates(id),
    sort_order      INTEGER NOT NULL,
    label           TEXT NOT NULL,
    is_required     BOOLEAN DEFAULT TRUE
);

CREATE TABLE possession_checklists (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    booking_id          BIGINT NOT NULL REFERENCES bookings(id),
    unit_id             BIGINT NOT NULL REFERENCES units(id),
    template_id         BIGINT REFERENCES possession_checklist_templates(id),
    possession_date     DATE NOT NULL,
    status              TEXT DEFAULT 'in_progress',
    completed_at        TIMESTAMPTZ,
    completed_by        TEXT,
    notes               TEXT,
    created_at          TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE possession_checklist_responses (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    checklist_id    BIGINT NOT NULL REFERENCES possession_checklists(id),
    item_id         BIGINT REFERENCES possession_checklist_template_items(id),
    label           TEXT NOT NULL,
    is_required     BOOLEAN DEFAULT TRUE,
    checked         BOOLEAN DEFAULT FALSE,
    notes           TEXT
);

-- ----------------------------------------------------------------------------
-- document_templates / customer_documents (added at runtime today via
-- backend/auth/schema.py::ensure_tenant_schema — folded into the base schema
-- here since Postgres migrations should be explicit, not "run on every boot")
-- ----------------------------------------------------------------------------
CREATE TABLE document_templates (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code                TEXT UNIQUE,
    name                TEXT NOT NULL,
    kind                TEXT NOT NULL DEFAULT 'general',
    description         TEXT,
    body_html           TEXT NOT NULL,
    requires_booking    BOOLEAN NOT NULL DEFAULT TRUE,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_by          BIGINT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE customer_documents (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    doc_no                  TEXT NOT NULL UNIQUE,
    customer_id             BIGINT NOT NULL REFERENCES customers(id),
    booking_id              BIGINT REFERENCES bookings(id),
    template_id             BIGINT REFERENCES document_templates(id),
    title                   TEXT NOT NULL,
    body_html               TEXT NOT NULL,
    visible_to_customer     BOOLEAN NOT NULL DEFAULT TRUE,
    created_by              BIGINT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at              TIMESTAMPTZ
);

-- ============================================================================
-- Indexes (matches backend/db/schema.sql today; a few added for FK columns
-- that had no covering index — Postgres, unlike SQLite, does not need an
-- index for the referencing side of a FK, but hot lookup columns still do).
-- ============================================================================
CREATE INDEX idx_units_project ON units(project_id);
CREATE INDEX idx_units_status ON units(status);
CREATE INDEX idx_installments_booking ON installments(booking_id);
CREATE INDEX idx_installments_due ON installments(due_date);
CREATE INDEX idx_installments_status ON installments(status);
CREATE INDEX idx_payments_booking ON payments(booking_id);
CREATE INDEX idx_payments_customer ON payments(customer_id);
CREATE INDEX idx_bookings_unit ON bookings(unit_id);
CREATE INDEX idx_bookings_customer ON bookings(customer_id);
CREATE INDEX idx_bookings_project ON bookings(project_id);
CREATE INDEX idx_po_vendor ON purchase_orders(vendor_id);
CREATE INDEX idx_po_project ON purchase_orders(project_id);
CREATE INDEX idx_site_logs_project ON site_logs(project_id);
CREATE INDEX idx_site_logs_date ON site_logs(log_date);
CREATE INDEX idx_unit_holds_unit ON unit_holds(unit_id);
CREATE INDEX idx_unit_holds_status ON unit_holds(status);
CREATE INDEX idx_hold_tx_hold ON hold_transactions(hold_id);
CREATE INDEX idx_pit_project ON project_installment_templates(project_id);
CREATE INDEX idx_pitr_template ON project_installment_template_rules(template_id);
CREATE INDEX idx_contractor_assign_project ON contractor_assignments(project_id);
CREATE INDEX idx_inv_mov_item ON inventory_movements(item_id);
CREATE INDEX idx_poss_check_unit ON possession_checklists(unit_id);
CREATE INDEX idx_customer_documents_customer ON customer_documents(customer_id);
CREATE INDEX idx_customers_cnic ON customers(cnic) WHERE cnic IS NOT NULL;
CREATE INDEX idx_ledger_entries_date ON ledger_entries(entry_date);
CREATE INDEX idx_ledger_entries_project ON ledger_entries(project_id);
