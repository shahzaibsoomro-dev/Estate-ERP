PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS company_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    location TEXT,
    description TEXT,
    area TEXT,
    city TEXT,
    start_date TEXT,
    expected_end_date TEXT,
    status TEXT DEFAULT 'under_construction',
    current_progress INTEGER DEFAULT 0,
    number_of_floors INTEGER DEFAULT 0,
    number_of_units INTEGER DEFAULT 0,
    project_attributes TEXT DEFAULT '[]',
    total_area_ghaz REAL,
    estimated_cost INTEGER
);

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    father_name TEXT,
    description TEXT,
    residential_address TEXT,
    cnic TEXT UNIQUE,
    contact_number TEXT,
    emergency_contact_number TEXT,
    email TEXT,
    created_at TEXT DEFAULT (date('now'))
);

CREATE TABLE IF NOT EXISTS agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    contact TEXT,
    default_rate_pct REAL DEFAULT 2.0,
    status TEXT DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS units (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    unit_no TEXT NOT NULL,
    description TEXT,
    unit_type TEXT DEFAULT 'Flat',
    residential_type TEXT,
    floor_number INTEGER DEFAULT 1,
    area_ghaz REAL,
    block_tower TEXT,
    bedrooms INTEGER,
    bathrooms INTEGER,
    status TEXT DEFAULT 'available',
    base_sale_price INTEGER,
    final_sold_price INTEGER,
    booking_amount_required INTEGER,
    furnishing_status TEXT,
    unit_attributes TEXT DEFAULT '[]',
    additional_requirements TEXT,
    possession_date TEXT,
    hold_customer_id INTEGER,
    hold_until TEXT,
    hold_notes TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id),
    FOREIGN KEY (hold_customer_id) REFERENCES customers(id),
    UNIQUE(project_id, unit_no)
);

CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_no TEXT UNIQUE NOT NULL,
    customer_id INTEGER NOT NULL,
    unit_id INTEGER NOT NULL,
    project_id INTEGER NOT NULL,
    agent_id INTEGER,
    booking_date TEXT NOT NULL,
    base_sale_price INTEGER NOT NULL,
    final_sale_price INTEGER NOT NULL,
    booking_amount INTEGER NOT NULL,
    possession_date TEXT,
    status TEXT DEFAULT 'active',
    payment_mode TEXT DEFAULT 'Cheque',
    notes TEXT,
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    FOREIGN KEY (unit_id) REFERENCES units(id),
    FOREIGN KEY (project_id) REFERENCES projects(id),
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);

CREATE TABLE IF NOT EXISTS installments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id INTEGER NOT NULL,
    customer_id INTEGER NOT NULL,
    unit_id INTEGER NOT NULL,
    installment_no INTEGER NOT NULL,
    due_date TEXT NOT NULL,
    amount INTEGER NOT NULL,
    paid_amount INTEGER DEFAULT 0,
    remaining_amount INTEGER NOT NULL,
    type TEXT DEFAULT 'Monthly',
    notes TEXT,
    status TEXT DEFAULT 'pending',
    FOREIGN KEY (booking_id) REFERENCES bookings(id),
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    FOREIGN KEY (unit_id) REFERENCES units(id)
);

CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    booking_id INTEGER NOT NULL,
    installment_id INTEGER,
    amount INTEGER NOT NULL,
    payment_date TEXT NOT NULL,
    payment_method TEXT DEFAULT 'Cash',
    bank TEXT,
    reference_number TEXT,
    received_by TEXT DEFAULT 'Admin',
    notes TEXT,
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    FOREIGN KEY (booking_id) REFERENCES bookings(id),
    FOREIGN KEY (installment_id) REFERENCES installments(id)
);

CREATE TABLE IF NOT EXISTS receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id INTEGER NOT NULL UNIQUE,
    receipt_no TEXT UNIQUE NOT NULL,
    issued_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (payment_id) REFERENCES payments(id)
);

CREATE TABLE IF NOT EXISTS booking_cancellations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id INTEGER NOT NULL,
    cancelled_at TEXT DEFAULT (datetime('now')),
    reason TEXT,
    total_paid INTEGER NOT NULL,
    forfeit_amount INTEGER NOT NULL,
    refund_amount INTEGER NOT NULL,
    forfeit_pct REAL NOT NULL,
    FOREIGN KEY (booking_id) REFERENCES bookings(id)
);

CREATE TABLE IF NOT EXISTS vendors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    contact TEXT,
    category TEXT,
    status TEXT DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS budget_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS project_budget_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    category_id INTEGER NOT NULL,
    planned_amount INTEGER NOT NULL,
    revision_no INTEGER DEFAULT 1,
    is_active INTEGER DEFAULT 1,
    notes TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id),
    FOREIGN KEY (category_id) REFERENCES budget_categories(id)
);

CREATE TABLE IF NOT EXISTS purchase_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    po_no TEXT UNIQUE NOT NULL,
    vendor_id INTEGER NOT NULL,
    project_id INTEGER NOT NULL,
    budget_category_id INTEGER,
    category TEXT,
    material TEXT NOT NULL,
    quantity TEXT,
    unit_cost INTEGER,
    total INTEGER NOT NULL,
    order_date TEXT NOT NULL,
    expected_delivery_date TEXT,
    status TEXT DEFAULT 'ordered',
    grn_status TEXT DEFAULT 'pending',
    site TEXT,
    notes TEXT,
    FOREIGN KEY (vendor_id) REFERENCES vendors(id),
    FOREIGN KEY (project_id) REFERENCES projects(id),
    FOREIGN KEY (budget_category_id) REFERENCES budget_categories(id)
);

CREATE TABLE IF NOT EXISTS vendor_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vendor_id INTEGER NOT NULL,
    purchase_order_id INTEGER,
    amount INTEGER NOT NULL,
    payment_date TEXT NOT NULL,
    payment_method TEXT DEFAULT 'Bank Transfer',
    reference_number TEXT,
    notes TEXT,
    FOREIGN KEY (vendor_id) REFERENCES vendors(id),
    FOREIGN KEY (purchase_order_id) REFERENCES purchase_orders(id)
);

CREATE TABLE IF NOT EXISTS agent_commissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id INTEGER NOT NULL UNIQUE,
    agent_id INTEGER NOT NULL,
    rate_pct REAL NOT NULL,
    commission_amount INTEGER NOT NULL,
    paid_amount INTEGER DEFAULT 0,
    status TEXT DEFAULT 'earned',
    FOREIGN KEY (booking_id) REFERENCES bookings(id),
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);

CREATE TABLE IF NOT EXISTS agent_commission_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    commission_id INTEGER NOT NULL,
    amount INTEGER NOT NULL,
    payment_date TEXT NOT NULL,
    notes TEXT,
    FOREIGN KEY (commission_id) REFERENCES agent_commissions(id)
);

CREATE TABLE IF NOT EXISTS investors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    cnic TEXT,
    mobile_number TEXT,
    email TEXT,
    description TEXT,
    status TEXT DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS investor_agreements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    investor_id INTEGER NOT NULL,
    project_id INTEGER,
    investor_type TEXT NOT NULL,
    investment_amount INTEGER NOT NULL,
    investment_date TEXT NOT NULL,
    monthly_return_pct REAL,
    profit_share_pct REAL,
    status TEXT DEFAULT 'active',
    FOREIGN KEY (investor_id) REFERENCES investors(id),
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS investor_contributions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agreement_id INTEGER NOT NULL,
    amount INTEGER NOT NULL,
    contribution_date TEXT NOT NULL,
    notes TEXT,
    FOREIGN KEY (agreement_id) REFERENCES investor_agreements(id)
);

CREATE TABLE IF NOT EXISTS investor_distributions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agreement_id INTEGER NOT NULL,
    amount INTEGER NOT NULL,
    distribution_date TEXT NOT NULL,
    notes TEXT,
    FOREIGN KEY (agreement_id) REFERENCES investor_agreements(id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id INTEGER,
    action TEXT NOT NULL,
    details TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_units_project ON units(project_id);
CREATE INDEX IF NOT EXISTS idx_units_status ON units(status);
CREATE INDEX IF NOT EXISTS idx_installments_booking ON installments(booking_id);
CREATE INDEX IF NOT EXISTS idx_installments_due ON installments(due_date);
CREATE INDEX IF NOT EXISTS idx_payments_booking ON payments(booking_id);
CREATE INDEX IF NOT EXISTS idx_bookings_unit ON bookings(unit_id);
CREATE TABLE IF NOT EXISTS site_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    log_date TEXT NOT NULL,
    engineer TEXT NOT NULL,
    workers_skilled INTEGER DEFAULT 0,
    workers_unskilled INTEGER DEFAULT 0,
    material_used TEXT,
    work_done TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE INDEX IF NOT EXISTS idx_po_vendor ON purchase_orders(vendor_id);
CREATE INDEX IF NOT EXISTS idx_po_project ON purchase_orders(project_id);
CREATE INDEX IF NOT EXISTS idx_site_logs_project ON site_logs(project_id);
CREATE INDEX IF NOT EXISTS idx_site_logs_date ON site_logs(log_date);
