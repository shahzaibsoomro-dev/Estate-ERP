# Haven Builders ERP — Desktop Edition
### Version 4.0 | FastAPI + SQLite Backend

Construction / real-estate ERP with project management, unit inventory, sales,
installments, procurement, vendors, agents, investors, and budgeting.

See **[Details.md](Details.md)** for business logic and module flows.

---

## Quick Start

**Python 3.9+** required.

### Windows
Double-click **`run.bat`**

### Mac / Linux
```bash
chmod +x run.sh stop.sh
./run.sh
```

### Manual
```bash
pip install -r requirements.txt
python -m uvicorn backend.main:app --host 0.0.0.0 --port 5050
```
Open **http://localhost:5050** — the public homepage. Staff sign in at `/login` and land in the ERP (`/app`); owners land in their portal (`/portal`).

To stop: `stop.bat` / `stop.sh`, or close the server window.

---

## Companies, roles & subscriptions

The system is **multi-company (SaaS)**. Each real-estate company gets its **own SQLite database** (`db/tenants/<slug>.db`); logins, subscriptions and payments live in the platform database (`db/platform.db`). An existing single-company install is migrated automatically on first start: `db/haven.db` becomes company #1 (Enterprise plan, 30-day period) and any existing accounts move to the platform database.

| Role | Who | Where | Can do |
|------|-----|-------|--------|
| **Super admin** | Developers / platform team | `/console` | Create companies and their first admin, plans & prices, record/void subscription payments, suspend/reactivate, reset or unlock any admin/employee, audit log, API docs. **Support mode** opens a company's ERP (logged and visible to that company). |
| **Admin** | Real-estate company owners/managers | `/app` | Everything in their company's ERP, plus **Employees & Access**, customer portal logins, subscription status & payment history. |
| **Employee** | Staff created by the admin | `/app` | Only the pages ticked by the admin, per action (**view / add / edit / delete**), and only the **projects** assigned (or all). Presets: sales, recovery, accountant, site engineer, read-only. |
| **Customer** | Unit owners | `/portal` | Their own bookings, payment plan, payments and documents. Sign in with email or CNIC. |

**Subscriptions** (recorded manually by the super admin — bank transfer, cash, cheque, JazzCash, Easypaisa…):

- *Trial* → *Active* → *Grace period* (default 7 days after the period ends, everything still works, banner shown) → *Expired*: **read-only** for admins and employees; the owner portal keeps working.
- *Suspended* (by super admin): admins and employees are signed out and cannot sign in.
- Recording a payment extends the period by N months/years (continuing seamlessly if paid on time or in grace); voiding the latest payment rolls it back.
- Plan limits (max employees / projects) are enforced when adding employees or projects.

**First run** — start the server and open **http://localhost:5050/setup** on the same computer (the sign-in page redirects there automatically). Create:

1. your **super admin** account (platform console), and
2. a **company admin** for your existing data (projects, units, customers, bookings), optionally renaming the company.

The setup page works only while no super admin exists, and only from the server computer itself (requests through a reverse proxy are refused). Set `ERP_ALLOW_REMOTE_SETUP=1` only if you must run it from another machine. Terminal alternatives: `python -m backend.manage create-superadmin`, or `ERP_BOOTSTRAP_SUPERADMIN_EMAIL` / `ERP_BOOTSTRAP_SUPERADMIN_PASSWORD`.

Other commands: `list-companies`, `create-user --role admin --company <slug>`, `reset-password`, `list-users`, `demo-users` (development only).

**Security model**

- Passwords hashed with scrypt; minimum 10 characters with letters and numbers, not containing the username; one-time passwords force a change at first sign-in.
- Server-side sessions in an `HttpOnly`, `SameSite=Lax` cookie (`Secure` over HTTPS; force with `ERP_COOKIE_SECURE=1`). 2-hour idle / 12-hour absolute timeout; support sessions 2 hours.
- **Deny by default** (`backend/auth/middleware.py`): every path is classified (public / customer / console / company); every business API is mapped to a page + action in `backend/auth/permissions.py` — routes not in the map are admin-only.
- **Project scoping** (`backend/auth/scope.py`) for project-limited employees: list filters are forced to their projects, records from other projects return 403, request bodies referencing other projects are rejected, and JSON lists are filtered. Company-wide pages (cashbook, reports, parties, activity) require all-project access.
- Company data is isolated by database file; customer APIs never take a customer id from the request.
- CSRF token + Origin check on every write; login throttling (5 failures per account / 20 per IP in 15 minutes, admins/super admins can unlock).
- Security headers (CSP, frame, nosniff, referrer, HSTS on HTTPS). Sign-ins, access changes, payments and support sessions are written to the platform audit log with user and IP.
- The server binds to `127.0.0.1` by default. To serve other machines set `ERP_HOST=0.0.0.0` **and** put it behind HTTPS (Caddy / nginx).

## Documents

*Sales & CRM → Documents* generates printable documents (payment plan, allotment letter, statement of account, demand notice) from HTML templates with `{{placeholders}}`. Staff choose whether each document appears in the owner portal and can revoke it later. Templates are sanitised (no scripts, forms, frames or event handlers) and every value is HTML-escaped.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests            # auth, roles, permissions, isolation, subscriptions (temp DB copies)
ERP_SCRIPT_EMAIL=admin@yourco.com ERP_SCRIPT_PASSWORD=... python -m backend.verify   # company admin; needs a running server
```

## Database

SQLite file: **`db/haven.db`** — created and seeded automatically on first run.

Schema v2 lives in **`backend/db/schema.sql`**. Sample data: **`backend/db/seed.py`**.

**Reset data:** delete `db/haven.db` and restart the server.

---

## Project Structure

```
backend/
  main.py           FastAPI app
  config.py         paths and defaults
  database.py       SQLite helpers
  db/schema.sql     table definitions
  db/seed.py        sample data
  routers/          HTTP endpoints
  services/         business logic
  auth/             sessions, roles, permissions, project scoping, middleware
  saas/             companies, plans, subscriptions, platform DB
  documents/        document templates + rendering
  manage.py         account management CLI
static/
  home.html         public homepage
  login.html        sign-in / change password
  setup.html        first-run account setup
  portal.html       customer (owner) portal
  console.html      super admin platform console
  index.html        staff ERP app
tests/              security tests
Details.md          business rules (non-code)
```

---

## API Overview

| Area | Endpoints |
|------|-----------|
| Core | `/api/health`, `/api/dashboard`, `/api/settings` |
| Projects & units | `/api/projects`, `/api/units` |
| Sales | `/api/customers`, `/api/bookings`, `/api/payments` |
| Recovery | `/api/recovery`, `/api/demand-notices` |
| Procurement | `/api/vendors`, `/api/purchase-orders`, `/api/vendor-payments` |
| Finance | `/api/budget/*`, `/api/agents`, `/api/investors` |
| Auth | `/api/auth/login`, `/api/auth/logout`, `/api/auth/me`, `/api/auth/change-password` |
| Console (super admin) | `/api/console/*` — companies, subscriptions, payments, plans, support |
| Company admin | `/api/company/employees`, `/api/company/subscription`, `/api/company/activity` |
| Portal access | `/api/portal-access` |
| Documents | `/api/document-templates`, `/api/customer-documents`, `/documents/{id}` |
| Customer (self) | `/api/me/overview`, `/api/me/documents` |
| Public | `/api/public/overview` |
| Stubs (UI compat) | `/api/site-logs`, `/api/ledger`, `/api/reports/*` |

Interactive docs: **http://localhost:5050/docs** (super admin only)

---

*Haven Builders ERP — Internal Use Only*
