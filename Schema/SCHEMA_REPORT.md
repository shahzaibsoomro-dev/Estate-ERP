# PostgreSQL Schema — Design Report

This documents the PostgreSQL schema in this folder: what it replaces, every
design decision made translating it from SQLite, and what's still open. It
covers `00_extensions.sql`, `01_platform_schema.sql`, and `02_tenant_schema.sql`.

Scanned source: `backend/db/schema.sql` (41 tables), `backend/auth/schema.py`
(2 more tables + 4 columns added at runtime), `backend/saas/schema.py`
(11 platform tables) — 54 tables total across today's SQLite databases.

---

## 1. Multi-tenancy model: schema-per-tenant

Today: one SQLite **file** per company (`db/tenants/<slug>.db`), routed by
`backend/database.py`'s `current_db_path` ContextVar, plus one `platform.db`
for logins/billing.

In Postgres: one **schema** per company, inside a single database.

```
mydb
├── platform            (companies, plans, subscriptions, users, sessions, audit)
├── tenant_acme          (projects, units, bookings, ... — company "Acme")
├── tenant_greenview      (same tables, company "Greenview")
└── tenant_...
```

**Why this over the alternatives:**

| Option | Isolation | Ops complexity | Fit here |
|---|---|---|---|
| **Schema-per-tenant** (chosen) | Strong — a query can't leak across schemas by accident | One schema to create/migrate per signup; fine up to low hundreds of tenants | Matches your current file-per-tenant mental model almost exactly — smallest conceptual jump |
| Shared tables + `tenant_id` column | Weak — depends on every query filtering correctly (RLS can backstop this) | Simplest at very large tenant counts (1000s) | Overkill for a real-estate ERP that won't have thousands of tenants soon, and riskier for financial data |
| Database-per-tenant (separate Postgres DBs) | Strongest | Highest — connection pooling, migrations, and backups all multiply per tenant | Only worth it if a client demands physical DB separation (e.g., contractual/compliance reasons) |

If you ever cross a few hundred tenants and schema management becomes
unwieldy, migrating from schema-per-tenant to shared-tables-with-RLS is a
well-trodden path — easier to do that later than to have started with the
weaker isolation model and try to retrofit isolation after a leak.

**Provisioning a new tenant** (what today's "create a new `.db` file and run
`schema.sql`" becomes):

```sql
CREATE SCHEMA tenant_acme;
SET search_path TO tenant_acme;
\i Schema/02_tenant_schema.sql
RESET search_path;
INSERT INTO platform.companies (name, slug, schema_name) VALUES ('Acme Builders', 'acme', 'tenant_acme');
```

Your app's `current_db_path` ContextVar becomes a `current_tenant_schema`
ContextVar that issues `SET search_path TO tenant_acme, public` on the
connection per request, instead of opening a different file. Everything
downstream of that (unqualified table names in queries) keeps working
unchanged.

---

## 2. Type translation reference

SQLite is dynamically typed and let this schema get away with several things
Postgres won't. Every mapping below is a deliberate choice, not a mechanical
1:1 swap — the "why" matters if you're reviewing this.

| SQLite (was) | Postgres (now) | Why |
|---|---|---|
| `INTEGER PRIMARY KEY AUTOINCREMENT` | `BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY` | `IDENTITY` is the modern standard (vs `SERIAL`); `BIGINT` avoids ever hitting the 2.1B row ceiling of `INTEGER`/`SERIAL` on a table like `payments` or `audit_log` that grows forever |
| Money columns as `INTEGER` (e.g. `base_sale_price`, `amount`) | `NUMERIC(16,2)` | SQLite's `INTEGER` gave you exact whole-rupee math by accident; Postgres `NUMERIC` gives you **exact decimal math on purpose** (no float rounding), and headroom for paisa/cents if you ever need sub-unit precision. This is the single highest-value change for a system whose whole job is tracking money. |
| Percentage/rate columns as `REAL` (e.g. `rate_pct`, `forfeit_pct`) | `NUMERIC(6,3)` | `REAL` is binary floating point — `2.5%` doesn't always round-trip exactly. Rates compound into commission and investor-return calculations, so exactness matters here too. |
| Quantities as `REAL` (e.g. `area_ghaz`, `min_stock`, movement `quantity`) | `NUMERIC(14,3)` | Same exactness argument, lower stakes than money but still additive fields (stock levels) where float drift accumulates over many movements. |
| Dates as `TEXT` (`'YYYY-MM-DD'`) | `DATE` | Real type gets you range queries, `date + interval`, and comparison operators without string-comparison tricks — replaces most of the 73 `strftime()`/`julianday()` call sites you'll be translating in the app layer. |
| Timestamps as `TEXT` (`datetime('now')`) | `TIMESTAMPTZ DEFAULT now()` | Stores an absolute instant instead of a naive local string — avoids ambiguity if the app server or a future multi-region deployment isn't always in the same timezone as Pakistan. |
| Boolean-ish `INTEGER` (0/1) (e.g. `is_active`, `is_public`, `checked`, `must_change_password`) | `BOOLEAN` | Self-documenting, and Postgres enforces only `TRUE`/`FALSE`/`NULL` — SQLite would silently accept `INTEGER` value `2` in that column. |
| Free-form JSON in `TEXT` (`project_attributes`, `unit_attributes`, `audit_log.details`, `platform_audit.details`) | `JSONB` | Native JSON querying/indexing (`->`, `->>`, `@>`), and validates it's actually valid JSON on write instead of silently storing garbage. Directly addresses the "site_logs will have dynamic and open fields" requirement noted in `db_overview.md`. |
| `TEXT ... COLLATE NOCASE` (`companies.slug`, `users.email`) | `CITEXT` (via the `citext` extension, `00_extensions.sql`) | Case-insensitive comparison and uniqueness without needing `LOWER()` on every query — direct drop-in replacement for `COLLATE NOCASE`. |
| IP address as `TEXT` (`auth_sessions.ip`, `login_attempts.ip`, `platform_audit.ip`) | `INET` | Validates it's actually an IP, and supports subnet queries later if you ever want to rate-limit by CIDR range. |
| `CHECK` constraints on `status`/`role` columns | Kept as `CHECK (... IN (...))` | Postgres `CHECK` syntax is compatible as-is — no translation needed, these carried straight over. |
| `INSERT OR IGNORE` (seeding default plans) | `INSERT ... ON CONFLICT (code) DO NOTHING` | Direct Postgres equivalent for the one seed-data use case in this schema. |

### New `CHECK` constraints added

A few `status`/`type` columns were left as unconstrained `TEXT` in SQLite.
Rather than trust `Details.md`/`db_overview.md`'s documented value lists at
face value, every constraint below was checked against the actual
`backend/services/*.py` code that writes these columns — three of the
originally-drafted constraints didn't match what the app really stores and
were corrected:

| Column | Constraint added | Verified against |
|---|---|---|
| `projects.status` | `'planning'`, `'under_construction'`, `'completed'` | `backend/services/projects.py` |
| `units.status` | `'available'`, `'hold'`, `'sold'`, `'booked'`, `'possession_delivered'`, `'blocked'` | `backend/services/units.py:230` (`allowed = {...}` set) — **note: no `'cancelled'` value exists for units; it's `'blocked'` instead**, which the docs didn't mention |
| `bookings.status` | `'active'`, `'completed'`, `'cancelled'` | `backend/services/bookings.py` |
| `installments.type` | `'Booking'`, `'Monthly'`, `'Quarterly'`, `'Possession'` | `backend/db/seed.py`, `backend/simulate.py` |
| `installments.status` | `'scheduled'`, `'pending'`, `'partial'`, `'paid'`, `'overdue'`, `'cancelled'` | `backend/services/installment_templates.py`, `backend/services/bookings.py:202` — **the docs list `pending/paid/overdue` only; actual code also uses `'scheduled'` (before an installment's trigger fires) and `'cancelled'` (on booking cancellation)** |
| `purchase_orders.status` | `'ordered'`, `'delivered'`, `'closed'`, `'cancelled'` | `backend/services/vendors.py` (DB-write call sites only — that file also computes a richer *display* status like `'draft'`/`'approved'`/`'payment_pending'` in Python, never written to this column) |
| `investor_agreements.status` | `'active'`, `'completed'`, `'withdrawn'` | `backend/services/capital.py:_person_status()` |
| `investor_agreements.investor_type` | `'Monthly Return'`, `'Profit Sharing'` | `backend/services/capital.py:_normalize_return_type()` |
| `ledger_entries.direction` | `'in'`, `'out'` | `backend/services/accounts.py:create_ledger_entry()` — **not `'debit'`/`'credit'` as the table's original column comment implied** |
| `hold_transactions.direction` | `'in'`, `'out'`, `'refund'` | `backend/services/holds.py`, `backend/services/accounts.py` — **`'refund'` is a real third value, easy to miss from the docs alone** |
| `inventory_movements.direction` | `'in'`, `'out'` | `backend/services/inventory.py` (normalizes `'adjust'` to `'in'`/`'out'` before insert) |

If your production data has slipped outside even these verified lists (e.g.
via a direct DB edit or an older code path), the migration script (section 4)
needs to fix the data before load — `COPY`/`INSERT` will reject any row that
violates a `CHECK` constraint.

### Deliberately *not* changed

- `quantity` on `purchase_orders` stays `TEXT` — it's already a free-text
  field in the source ("Quantity" as e.g. "50 bags") not a number.
- `template_id`/`template_rule_id` on `bookings`/`installments` — these
  forward-reference tables defined later in the file (SQLite didn't enforce
  the FK at all; Postgres needs the referenced table to exist first, so
  those two constraints are added via `ALTER TABLE ... ADD CONSTRAINT` at
  the bottom of the relevant section instead of inline).

---

## 3. What's genuinely new here (not in either SQLite schema)

- **`companies.schema_name`** replaces `companies.db_path` — a Postgres
  schema name instead of a filesystem path.
- A handful of indexes not present in the original `schema.sql` but implied
  by actual query patterns in `backend/routers`/`services` (foreign key
  columns that are filtered/joined on but had no index): `bookings.customer_id`,
  `bookings.project_id`, `payments.customer_id`, `installments.status`,
  `customers.cnic`, `ledger_entries.entry_date`/`project_id`. Postgres, unlike
  SQLite, doesn't require an index on a FK column to function, but these are
  worth having for query performance once tenants have real transaction
  volume — audit them against `EXPLAIN ANALYZE` output after go-live rather
  than trusting this list blindly.
- The two tables `backend/auth/schema.py` currently creates **on every
  server boot** (`document_templates`, `customer_documents`) and the four
  columns it patches in with `ALTER TABLE ... ADD COLUMN` if missing
  (`audit_log.user_id`, `audit_log.ip`, `ledger_entries.payment_method`,
  `ledger_entries.project_id`) are folded directly into the base tenant
  schema here. Postgres migrations should be explicit and versioned (see
  section 5), not re-applied speculatively on every process start the way
  the current SQLite bootstrap does.

## 4. What this schema does *not* solve

Carried over from `db_overview.md`'s "Known gaps" — this migration changes
the database engine, not the data model. These are still open regardless of
which database you're on:

- No refunds table beyond `booking_cancellations` (cancellation is modeled,
  partial refund workflow is not).
- `agents` has no FK-enforced link from `bookings.agent_id` bonus logic
  beyond `agent_commissions` — commission auto-calculation logic lives in
  the app layer, not the DB.
- Nothing auto-transitions `installments.status` to `overdue` when
  `due_date` passes — still a job for a scheduled task, not a DB trigger
  (though Postgres *could* do this with a scheduled `pg_cron` job querying
  `WHERE due_date < CURRENT_DATE AND status = 'pending'` if you want to move
  it into the DB later).
- `projects.number_of_units`/sold-available-hold counts can still drift from
  actual `units.status` — a materialized view or trigger to keep this in
  sync is a reasonable follow-up once you're on Postgres (SQLite makes
  triggers and views more awkward to maintain).

## 5. Migration mechanics — what actually needs to happen

1. **Provision**: run `00_extensions.sql` once, `01_platform_schema.sql`
   once, then `02_tenant_schema.sql` once per existing tenant (into its own
   new schema).
2. **Backfill data**: export each SQLite table to CSV (or use `pgloader`,
   which reads SQLite directly and can push straight into Postgres,
   including a lot of this type coercion automatically) and load into the
   matching Postgres table. Order matters — load in FK dependency order
   (`projects` → `customers`/`agents` → `units` → `bookings` → `installments`
   → `payments` → ...), or defer constraint checking during load with
   `SET CONSTRAINTS ALL DEFERRED` inside a transaction.
3. **Sanity-check the new `CHECK` constraints** (section 2) against real
   data before the load — a stray `status` value that predates the
   documented enum will fail the whole `INSERT`/`COPY`.
4. **Sequence sync**: after backfilling data with explicit IDs, run
   `SELECT setval('tablename_id_seq', (SELECT MAX(id) FROM tablename))` per
   table so `GENERATED ALWAYS AS IDENTITY` continues from the right number
   instead of colliding on the first new insert.
5. **App layer** (separate from this schema work, tracked in the earlier
   migration-scope discussion): swap the `sqlite3` driver for `psycopg`,
   translate `?` placeholders to `%s`, replace the 73 `strftime()`/
   `julianday()` call sites with Postgres date arithmetic, replace the 40
   `cursor.lastrowid` uses with `INSERT ... RETURNING id`, and replace
   `INSERT OR IGNORE`/`INSERT OR REPLACE` (11 call sites) with
   `ON CONFLICT`.
6. **Versioned migrations going forward**: once on Postgre, stop treating
   `ensure_tenant_schema()`-style "run this SQL on every boot, guarded by
   `IF NOT EXISTS`/column-existence checks" as the schema evolution strategy
   — adopt a real migration tool (Alembic, or even just numbered `.sql`
   files with a `schema_migrations` tracking table, which is a small step
   up from what `schema_meta` already does) so every tenant schema and the
   platform schema move through the same versioned steps instead of
   silently drifting.

---

## 6. File index

| File | Purpose |
|---|---|
| `00_extensions.sql` | `CREATE EXTENSION citext` (case-insensitive text, replaces `COLLATE NOCASE`) |
| `01_platform_schema.sql` | `platform` schema: companies, plans, subscriptions, billing, users, sessions, audit |
| `02_tenant_schema.sql` | Per-tenant business schema template: projects through possession checklists |
| `SCHEMA_REPORT.md` | This file |
