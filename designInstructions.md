# Haven Builders ERP — Design Instructions

**Product:** Construction / real-estate ERP (multi-project flat sales + finance + site ops)  
**Currency:** PKR · **Locale:** Pakistan (CNIC format, phone +92)

---

## Global layout (all pages)

### Sidebar
- Logo: company name + “ERP”
- Collapsible nav groups: **Projects · Sales · Operations · Finance · Settings**
- Active item highlight
- Badge on **Recovery** showing overdue count (e.g. red `7`)
- Bottom: logged-in user avatar, name, role (e.g. “Salman Arif · Administrator”)

### Top bar (every page)
- Page title + breadcrumb (e.g. `Sales / Customers`)
- **Project filter** dropdown: `All Projects` | `Haven Heights A` | `Haven Residencia` | …
- Primary CTA where relevant (e.g. `+ New Booking` on sales pages)
- Optional: date range picker on finance/dashboard pages

### Shared UI patterns
- **KPI cards** — label, big number, small subtitle, optional trend
- **Status badges** — green (paid/clear), yellow (pending/hold), red (overdue/danger), grey (draft/completed)
- **Tables** — sortable columns, row actions, search/filter row above
- **Modals** — forms for create/edit; wide modals for detail views
- **Empty states** — icon + short message + primary action
- **Toast** — success/error after save

---

## Dashboard

**Purpose:** Management overview — money and risk at a glance.  
**User:** Admin, director, accounts head.

### Filters
- Period: `This Month` | `This Quarter` | `This Year` | `Custom range`
- Project: `All` or single project

### KPI row (6 cards)
| Card | Sample data | Subtitle |
|------|-------------|----------|
| Received | PKR 12.4M | Customer payments in period |
| Spent | PKR 8.1M | POs, wages, expenses in period |
| Remaining | PKR 4.3M | Cash position / balance |
| Receivable | PKR 45.2M | Outstanding installments |
| Payable | PKR 6.8M | Vendor dues |
| Overdue cases | 7 | Installments past due |

### Charts (2 columns)
1. **Cash flow chart** — bar or line: Received vs Spent per month (last 12 months)
2. **Collection rate** — % of due installments collected per month

### Tables / widgets
- **Overdue installments** (top 10): Customer, Unit, Project, Amount, Days overdue, Phone, action `Remind`
- **Alerts panel**: low stock, budget overrun, hold expiring today, pending PO approvals (list with severity dot)

### Actions
- Click overdue row → jump to Recovery or customer detail
- `View all overdue` link

---

## Projects

### Project List

**Purpose:** See all developments and drill into units, budget, site.  
**User:** Admin, project manager.

#### Header
- Title: `Projects`
- Button: `+ New Project`

#### Project card (one per project)
| Field | Example |
|-------|---------|
| Name | Haven Heights – Block A |
| Location | Bahria Town, Lahore |
| Status badge | Active / Completed |
| Dates | 2023-01-15 → 2025-12-31 |
| Units | Total 120 · Sold 87 · Available 23 · Hold 10 |
| Progress bar | 72% construction |

#### Card actions
- `View Units` → Unit Inventory (filtered)
- `Budget` → Project Budget (filtered)
- `Site Logs` → Site Logs (filtered)
- `⋮` menu: Edit project, Archive

#### New project form (modal)
Name*, Location*, Start date, End date, Total units (planned), Status, Notes

---

### Unit Inventory

**Purpose:** Visual map of every flat/shop and its sale status.  
**User:** Sales, admin.

#### Header filters
- Project (required if not from top bar)
- Floor: All | 1–10
- Status: All | Available | Hold | Sold
- Type: All | 2 Bed | 3 Bed | Shop

#### Summary tiles (3)
Sold count · Available count · On hold count

#### Main content
- **Floor sections** — “Floor 3 — 8 units”
- **Unit tiles** in a grid:
  - Green = Available, Yellow = Hold, Red = Sold
  - Show: unit no (e.g. `A-014`), type, sqft on hover or small text

#### Unit detail (modal or slide-over)
**Unit info:** Unit no, Project, Type, Floor, Size, Facing, List price, Status  

**If sold/booked — add:**
- Customer: name, CNIC, phone, email
- Booking: date, sale price, agent, payment mode
- Summary: Total paid, Outstanding, % paid (progress bar)
- Installment table: Due date, Type, Amount, Status, `Pay` on open rows
- Payment history: Date, Amount, Method, Receipt #

**If available:** `Book this unit` button  
**If hold:** Hold expiry date, held for (customer/name), `Release hold` / `Convert to booking`

---

### Project Budget

**Purpose:** Planned spend vs actual per project and category.  
**User:** Admin, project manager, accounts.

#### Header
- Project selector (required)
- Period: full project life / YTD / custom
- Button: `+ Add budget line` or `Edit budget`

#### KPI row
| Card | Example |
|------|---------|
| Total budget | PKR 850M |
| Spent to date | PKR 312M (37%) |
| Remaining | PKR 538M |
| Over budget? | Block C +12% (warning badge) |

#### Budget table
| Category | Planned | Actual | Variance | % used | Progress bar |
|----------|---------|--------|----------|--------|--------------|
| Structural steel | PKR 45M | PKR 48M | +PKR 3M | 107% | red |
| Cement | PKR 12M | PKR 9M | −PKR 3M | 75% | green |
| Labor | PKR 28M | PKR 22M | −PKR 6M | 79% | blue |
| Tiles & finishing | PKR 18M | PKR 0 | — | 0% | grey |

Categories: Steel, Cement, Sand/Aggregates, Electrical, Tiles, Labor, Misc.

#### Drill-down
- Click category → list of POs and expenses in that category

---

## Sales

### Bookings / Cancellations

**Purpose:** Create sales and handle cancelled flats.  
**User:** Sales staff, admin.

#### Tab 1: New Booking
Two-column layout.

**Left — forms**
1. **Customer:** Name*, CNIC*, Phone, Email, Address, Next of kin (name + relation)
2. **Unit & pricing:** Project*, Unit* (available only), Booking date, Sale price*, Down payment*, Agent (dropdown), Payment mode
3. **Installment plan:** Repeatable rows — Amount, Due date, Type (Booking / Monthly / Stage), Notes; `+ Add row`

**Right — summary card**
Unit, Sale price, Down payment, Remaining, % upfront, installment count  
Buttons: `Reset` · `Confirm booking` (primary)

#### Tab 2: All Bookings (table)
| Booking # | Date | Customer | Unit | Project | Sale price | Paid | Outstanding | Agent | Status | Actions |
|-----------|------|----------|------|---------|------------|------|-------------|-------|--------|---------|
| BK-1042 | 2025-01-15 | Ahmed Raza | A-001 | Haven Heights | 8.5M | 3.0M | 5.5M | None | Active | View · Print |

Status badge: Active · Completed · Cancelled · Transferred

#### Tab 3: Cancellations
| Cancel date | Customer | Unit | Paid to date | Refund | Forfeit | Unit now | Cancelled by |
|-------------|----------|------|--------------|--------|---------|----------|--------------|
| 2025-04-10 | Sara Khan | B-003 | 2.5M | 2.0M | 0.5M | Available | Admin |

#### Cancel booking flow (modal wizard)
1. Select booking → show paid summary  
2. Fields: Reason*, Refund amount, Forfeit amount, New unit status (Available / Hold)  
3. Checkbox: Reverse broker commission  
4. Confirm with warning text

---

### Customers

**Purpose:** Client register — contact info, units, payment standing.  
**User:** Sales, recovery, admin.

#### Header
- Search (name, CNIC, phone)
- `+ Add customer` · `Export list`

#### Summary tiles
Total customers · Overdue count · On track / cleared count

#### Customer table
| Customer | CNIC | Units | Total value | Paid | Outstanding | Last payment | Status | Actions |
|----------|------|-------|-------------|------|-------------|--------------|--------|---------|
| Ahmed Raza | 35202-… | A-001 | 8.5M | 3.0M | 5.5M | 2025-05-02 | Overdue | View · Stmt |

#### Customer detail page (or large modal)
- **Profile:** all contact fields, edit button
- **Units & bookings** linked
- **Full payment schedule** across units
- **Payment history** with receipt download
- **Documents:** agreement, statements
- Actions: `Print statement` · `Send demand notice` · `Record payment`

#### Add / edit customer form
Name*, CNIC*, Phone, Email, Address, NOK name, NOK relation

---

### Recovery

**Purpose:** Chase overdue installments and record collections.  
**User:** Recovery team, accounts.

#### Header actions
`Bulk WhatsApp reminder` · `+ Record payment`

#### KPI row
Total receivable · Overdue amount · Collected (30 days) · Overdue case count

#### Ageing summary (optional bar)
30 days · 60 days · 90+ days buckets with amounts

#### Overdue table
| Customer | Unit | Project | Amount | Due date | Days overdue | Phone | Actions |
|----------|------|------|---------|----------|--------------|-------|---------|
| Ahmed Raza | A-001 | Haven Heights | 500K | 2025-03-15 | 45 | 0321-… | WA · Call · Pay |

Row color: yellow 1–30d, orange 31–60d, red 60+d

---

### Demand Notices

**Purpose:** Formal overdue letters — preview, print, email, WhatsApp.  
**User:** Recovery, admin.

#### Layout: split view

**Left — queue table**
| Customer | Unit | Amount | Days overdue | Last sent | Actions |
|----------|------|--------|--------------|-----------|---------|
| Ahmed Raza | A-001 | 500K | 45 | Never | Preview |

Header buttons: `Send all email` · `Download all PDF`

**Right — notice preview**
- Company letterhead (logo, address)
- To: customer name, CNIC, unit, project
- Body: amount due, due date, days overdue, late fee %, total payable, pay-within deadline
- Footer: bank details / contact

**Per-notice actions:** WhatsApp · Email · Print PDF

---

## Operations

### Procurement

**Purpose:** Purchase orders for materials and services.  
**User:** Site engineer, procurement, admin.

#### Header
`+ New purchase order`

#### KPI row
Total POs · Draft/pending approval · Completed · Payment pending

#### PO table
| PO # | Date | Vendor | Material | Qty | Total | Project | Site | GRN | Status | Actions |
|------|------|--------|----------|-----|-------|---------|------|-----|--------|---------|
| PO-2025-0142 | 2025-04-20 | Steel Corp | TMT bars | 50 T | 18.5M | Haven Heights | Block A | Pending | Approved | Approve · GRN |

Status: Draft → Approved → GRN done → Payment pending → Completed

#### New PO form
PO # (auto), Vendor*, Project*, Budget category, Material*, Qty, Unit cost, Total (calc), Site/block, Notes

---

### Vendors

**Purpose:** Supplier directory and what you owe them.  
**User:** Procurement, accounts.

#### Header
`+ Add vendor`

#### Summary tiles
Total payable · Total paid · Outstanding balance

#### Vendor table
| Vendor | Category | Phone | Total payable | Paid | Balance | Rating | Status | Actions |
|--------|----------|-------|---------------|------|---------|--------|--------|---------|
| Steel Corp Ltd | Steel | 0321-… | 18.5M | 10M | 8.5M | ⭐⭐⭐⭐ | Due | View |

#### Vendor detail page
- Contact info, bank details (future)
- **PO history** table
- **Payment history** table
- Actions: `Create PO` · `Record payment`

---

### Site Logs

**Purpose:** Daily construction diary per project.  
**User:** Site engineer, project manager.

#### Header
`+ Daily entry`

#### Summary (for selected project)
Block A progress % · Block B progress % · Workers on site today

#### Log feed (cards, newest first)
Each card:
- Project name · Date · Engineer name
- Labor: X skilled + Y unskilled
- Materials used (text)
- Work completed (text)
- Optional: photo thumbnails (future)

#### Daily entry form (modal)
Project*, Date*, Engineer*, Skilled workers, Unskilled workers, Materials used, Work done (textarea)

---

### Inventory

**Purpose:** Track material stock on site; low-stock alerts.  
**User:** Site engineer, store keeper.

#### Header
`+ Stock adjustment` · Project/site filter

#### Low-stock alerts (banner or cards)
“Cement — Block B: 12 bags remaining (reorder at 50)”

#### Inventory table
| Item | Unit | Project/site | In stock | Reorder level | Last movement | Status |
|------|------|--------------|----------|---------------|---------------|--------|
| OPC Cement | bags | Block A | 120 | 50 | 2025-05-02 | OK |
| TMT Steel | tons | Block A | 2.1 | 5 | 2025-04-30 | Low |

#### Stock movement log
Date, Item, In/Out, Qty, Source (GRN / site use / adjustment), Reference PO or site log

---

## Finance

### Cash Flow

**Purpose:** Monthly/yearly money in, out, and balance — main financial dashboard.  
**User:** Director, accounts head.

#### Filters
Period: Month / Quarter / Year / Custom · Project: All or one

#### KPI row (hero)
Received · Spent · Net · Closing balance

#### Chart
Stacked or grouped bars: Inflows vs Outflows by month (12 months)

#### Breakdown tables (tabs)
- **Inflows:** Customer payments, investor contributions, other
- **Outflows:** Vendor payments, labor, commissions, other
- Each row: Date, Description, Project, Amount, Reference #

#### Bank accounts summary (optional cards)
Account name, current balance, last transaction date

---

### Accounts / GL

**Purpose:** General ledger and journal entries.  
**User:** Accountant.

#### Header
`Trial balance` · `P&L` · `+ Journal entry`

#### Summary tiles
Total revenue · Total expenses · Net profit (period)

#### Ledger table
| Date | Narration | Debit | Credit | Balance | Account type | Project |
|------|-----------|-------|--------|---------|--------------|---------|
| 2025-05-02 | Installment — Ahmed Raza | — | 350K | 84.2M | Sales | Haven Heights |

Account types: Sales, Expense, Purchase, General

#### Journal entry form
Date, Account type, Project (optional), Narration*, Debit, Credit (one side required)

---

### Investors

**Purpose:** Track who invested in which project and their earnings.  
**User:** Director, finance.

#### Header
`+ Add investor` · `+ Record contribution` · `+ Record payout`

#### Summary tiles
Total capital deployed · Total distributed · Active investors

#### Investor table
| Investor | Type | Projects | Capital in | Earnings | Paid out | Balance due | Actions |
|----------|------|----------|------------|----------|----------|-------------|---------|
| Ali Ventures | Company | Heights A, Residencia | 50M | 8.2M | 5M | 3.2M | View |

Type: Individual / Company / Partner

#### Investor detail
- Profile + contact
- **Contributions:** Date, Project, Amount, Share %
- **Distributions:** Date, Project, Amount, Period
- **Project earnings summary:** Revenue, costs, profit, investor share (calculated)

---

### Agents

**Purpose:** Broker commissions on sales.  
**User:** Sales admin, accounts.

#### Header
`+ Add agent` · `Setup commission rules`

#### Summary tiles
Total agents · Commission earned · Unpaid commission

#### Agent list (cards or table)
| Agent | Rate | Projects | Bookings | Earned | Paid | Unpaid | Actions |
|-------|------|----------|----------|--------|------|--------|---------|
| Tariq Associates | 2% | Heights A | 14 | 12.6M | 12.6M | 0 | Pay · View |

#### Agent detail
- Commission per booking table: Booking, Unit, Sale price, Rate, Commission, Status (earned/paid/reversed)
- Pay commission action

---

### Reports

**Purpose:** One place to generate exports and PDFs.  
**User:** All roles (varies by report).

#### Report grid (tiles)
Each tile: icon, name, short description, `Generate` button

| Report | Description |
|--------|-------------|
| Customer statement | Payment history per customer |
| Installment schedule | Full plan per unit/booking |
| Ageing report | 30 / 60 / 90 day overdue buckets |
| Sales report | Project-wise bookings and collections |
| Expense report | Site and operational costs |
| Trial balance | DR/CR summary |
| Project P&L | Revenue vs cost per project |
| Budget vs actual | Per project, by category |
| Investor statement | Capital, earnings, payouts |

#### After generate
Show preview table or chart below + `Download PDF` · `Export Excel`

---

## Settings / Users

**Purpose:** Company config, users, roles, templates.  
**User:** Admin only.

### Tabs

#### Company
Company name, logo upload, address, phone, email, bank details (for notices), default late fee %, currency

#### Users
| Name | Username | Role | Status | Last login | Actions |
|------|----------|------|--------|------------|---------|
| Salman Arif | salman | Admin | Active | Today | Edit · Disable |

Roles: Admin, Sales, Accounts, Site Engineer, Recovery (view-only options)

`+ Add user` form: Name, Username, Email, Role, Password

#### Notice templates
Editor for demand notice / letter text with placeholders: `{customer}`, `{unit}`, `{amount}`, `{due_date}`

#### Commission defaults
Default broker rate, when commission is earned (on booking / on payment)

#### Audit log (read-only)
| Date/time | User | Action | Details |
|-----------|------|--------|---------|
| 2025-05-02 14:30 | salman | Payment recorded | A-001 · PKR 500K |

---

## Sample data for prototypes

Use consistent fake data across screens:

| Entity | Sample |
|--------|--------|
| Projects | Haven Heights A (Lahore), Haven Residencia (Karachi), Commercial Hub (Islamabad) |
| Units | A-001, B-014, C-022 |
| Customers | Ahmed Raza, Sara Khan, Fahad Siddiqui |
| Vendors | Steel Corp Ltd, City Cement Co |
| Agents | Tariq Associates (2%), Raza Realty (2.5%) |
| Amounts | 8,500,000 · 18,500,000 · format as PKR 8.5M where space is tight |

---

## Design notes

1. **Desktop-first** — primary users work on office PCs; min width ~1280px.
2. **Project context** — top-bar project filter should narrow data on most pages.
3. **PKR formatting** — use commas (8,500,000) or short form (8.5M / 1.2Cr).
4. **Status colors** — keep consistent: green = good, yellow = attention, red = overdue/risk..
5. **Open items** — cancellation refund rules and investor profit formula still TBD with client; use sensible defaults in prototype.

---

*Reference: current MVP in `static/index.html` · data model in `db_overview.md` · open questions in `Todo.txt`*
