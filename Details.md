# Haven Builders ERP — Project Details

**Purpose:** One place for management to see what is sold, what money came in, what was spent, what is still owed (to us and by us), and how each project is performing.

**Users:** Single **Admin** role only. No login for now — full access to everything.

**Currency & locale:** PKR · Pakistan (CNIC, local phone format)

---

## Mind map

```
                         HAVEN BUILDERS ERP
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
    PROJECTS              CUSTOMERS & SALES         FINANCE VIEW
        │                       │                       │
   ┌────┴────┐            ┌─────┴─────┐           Dashboard
   │         │            │           │           Reports
 Units    Budget      Customers   Bookings
   │         │            │           │
 Site     Procure-    Payments   Installments
 Logs     ment           │           │
          │          Receipts    Recovery
       Vendors              │     Demand notices
          │              Agents
       Investors         Actions (receipts, PDF, WA, email)
```

**Project** is the hub — units, budget, procurement, site work, sales, and (optionally) investors all tie to a project.

---

## What management should see at a glance

| Question | Answer comes from |
|----------|-------------------|
| What has been sold? | Units + active bookings |
| What money was received? | Customer payments & receipts |
| What money was spent? | Vendor payments & project expenses |
| What is still receivable? | Unpaid / partial installments |
| What is still payable? | Vendor balances (+ agent commission due) |
| How is each project doing? | Sales vs spend vs budget per project |

Inventory counts (sold, available, on hold) are always calculated from **actual unit status**, not typed in manually.

---

## Flow 1 — Sales (customer side)

```
Create Project → Add Units → Register Customer
       → Create Booking (pick customer + unit + pricing)
       → Generate Installment Plan
       → Collect Payments → Issue Receipt
       → (if late) Recovery / Demand Notice
       → Possession Delivered
```

### Unit lifecycle

```
Available → Hold → Booked → Sold → Possession Delivered
                ↘ Cancelled (if booking cancelled, unit returns to Available)
```

| Status | Meaning |
|--------|---------|
| **Available** | Open for sale |
| **Hold** | Reserved — customer in discussion; not yet booked |
| **Booked** | Sale agreement active; payment plan running |
| **Sold** | Sale complete (financially or legally closed) |
| **Possession Delivered** | Unit handed over to customer |
| **Cancelled** | Booking was cancelled; unit back in inventory |

### Booking rules

- Select an **existing customer** or create one first.
- Pricing is **fully flexible**: custom sale price, booking amount, any installment schedule (monthly, quarterly, balloon, possession charges, etc.).
- No fixed payment template — each booking defines its own plan.
- Every payment gets a **receipt** linked to the customer and booking.
- **Cancellation** is configurable. Default rule for now:
  - 30% of booking amount is **forfeited**
  - Remainder is **refunded**
  - Unit goes back to **Available**
  - Agent commission may be reversed (configurable)

### Installments

- Created when booking is confirmed.
- Status: **Pending → Partial → Paid**, or **Overdue** when due date passes and amount remains.
- Overdue is **automatic** (based on due date, not manual).
- Partial payments are allowed.

### Customer profile

- One customer can own **multiple units**.
- Profile always shows: units, total value, paid, outstanding, last payment, status (Overdue / On track / Cleared).

---

## Flow 2 — Construction (project side)

```
Create Project → Set Budget (by category, revisable)
       → Raise Purchase Order → Material Delivered
       → Pay Vendor → Close PO
       → Log Daily Site Activity
       → Compare Budget vs Actual Spend
```

### Procurement

```
PO Created → Ordered → Delivered → Vendor Paid → Closed (fully paid)
```

- Vendor **payable / paid / balance** is calculated from POs and payments.
- POs and spend are linked to a **project** (and budget category where possible).
- Partial deliveries and partial vendor payments — supported later; design allows it.

### Budget

- Per project, per **category** (Steel, Cement, Labor, etc. — categories are configurable).
- Planned amount can be **revised** over time.
- Actual spend comes from procurement and recorded expenses.
- Shows: planned, spent, variance, status (within budget / near limit / exceeded).

### Site logs

- Daily record: who reported, workers, work done, materials used, issues, progress %, remarks.
- Fields stay **open and flexible** for future needs.
- For **visibility and progress tracking** — not used to calculate finances directly.
- Photos/attachments — future.

---

## Flow 3 — Investment

```
Add Investor → (optionally link to Project)
       → Record Investment
       → Calculate / Record Returns
       → Make Distributions
```

### Investment types

| Type | How returns work |
|------|------------------|
| **Monthly return** | Fixed or flexible periodic payout (% or amount) |
| **Profit sharing** | Share of project or company profit |

- Return rules are **configurable** per investor or agreement.
- Project link is **optional** — some investors may be company-wide.
- Track: invested, returns received, outstanding return, status (Active / Completed / Withdrawn).

---

## Other modules (short)

### Agents (brokers)

```
Agent assigned on booking → Commission earned → Commission paid
```

- Agent is linked to the **booking**, not just free text.
- Commission rate and timing (on booking vs on payment) are **configurable**.
- Track earned vs paid vs **remaining due**.

### Recovery & demand notices

- List all **overdue** installments.
- Send reminders (WhatsApp, email) and generate **demand notice** letters.
- Ageing buckets: 30 / 60 / 90+ days.

### Dashboard

- Company-wide or **filter by one project**.
- KPIs: receivable, payable, overdue count, collections, sales, spend.
- Quick view of overdue cases and alerts (low budget, overdue vendors, etc.).

### Reports

- Filter by **project** and **date range**.
- Examples: customer statement, installment schedule, ageing, sales, budget vs actual, investor statement.
- Export to **PDF** and **Excel**.

### Actions (shared across modules)

One place for document and communication tasks — reused everywhere, not rebuilt per screen:

- Generate receipt
- Generate customer statement
- Generate demand notice
- Send email / WhatsApp
- Export PDF / Excel / print

---

## Money in vs money out

| Direction | Examples |
|-----------|----------|
| **Money in** | Customer installment payments, booking amounts |
| **Money out** | Vendor payments, agent commission, investor distributions, wages/expenses |

Both directions need a clear record and audit trail.

---

## Business rules — keep configurable

Do not hardcode these; store as settings so they can change:

- Cancellation forfeit % (default 30%)
- Late fee on demand notices
- Default agent commission %
- Investor return formulas
- Notice letter templates

---

## Audit & records

- Every payment → receipt.
- Financial changes (payment, cancellation, refund, vendor pay) → **audit trail** (what happened, when).
- Documents (agreements, statements, notices) linked to the related customer, booking, or payment.

---

## Out of scope for now

- Login, passwords, multiple user roles
- Full double-entry accounting (ledger hook planned for later)
- Customer self-service portal (preview only until later)
- WhatsApp/email live integration (generate content first; send manually or integrate later)

---

## Open questions (confirm with client when possible)

1. **Hold** — always tied to a named customer, or can be internal block?
2. **Booked vs Sold** — exact moment each status applies.
3. **Dashboard payable** — vendors only, or include agents and investor payouts?
4. **Investor profit share** — exact formula per project.
5. **Cancellation edge cases** — refund from booking amount only or from total paid?

Until confirmed, use the defaults described above.

---

*Reference: field lists in `db_overview.md` · UI ideas in `designInstructions.md`*
