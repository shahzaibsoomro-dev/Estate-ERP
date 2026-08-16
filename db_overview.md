# Database Overview

**SQLite** file: `db/haven.db` · Schema & seed: `db/seed.py` · Reset: delete `haven.db` and restart.

---

## Tables (11)

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `projects` | Buildings/phases | name, location, total_units, sold/available/hold counts, progress % |
| `units` | Flats/shops | project_id, unit_no, type, floor, price, status (`available`/`hold`/`sold`) |
| `customers` | Buyers | name, cnic (unique), phone, email, address, nok_name, nok_rel |
| `bookings` | Unit sale | unit_id, customer_id, sale_price, down_payment, agent (text), dates |
| `installments` | Payment schedule | booking_id, amount, due_date, type, status (`pending`/`paid`/`overdue`) |
| `payments` | Money received | installment_id, amount, paid_date, method, receipt_no |
| `vendors` | Suppliers | name, category, phone, email, rating |
| `purchase_orders` | Procurement | vendor_id, project_id, material, total, grn_status, status |
| `site_logs` | Daily site diary | project_id, engineer, workers, material_used, work_done |
| `agents` | Brokers | name, rate %, commission_earned, commission_paid |
| `ledger` | Simple GL | entry_date, narration, debit, credit, balance, account_type |

---

## How data connects

```
projects → units → bookings → installments → payments
                ↘ customers ↗
projects → purchase_orders → vendors
projects → site_logs
ledger ← (auto on booking DP + payment only)
agents — NOT linked by FK (bookings.agent is free text)
```

**On new booking:** customer → booking → unit=`sold` → installments → ledger credit (DP).  
**On payment:** payment → installment=`paid` → ledger credit.

---

## Known gaps

- No booking **cancellation** or refunds
- **Agents** not FK-linked to bookings; commission not auto-calculated
- **Overdue** status not auto-set when due date passes
- **Ledger** not linked to payments/POs (weak audit trail)
- **PO payments** and **GRN** not fully modeled
- No **investors**, **budgets**, **users**, or **documents** tables
- Project sold/available/hold counts can **drift** from real unit status
- Seed quirk: many units marked `sold` but only 7 have bookings

---

## Suggested new tables

| Area | Add |
|------|-----|
| Cancellations | `bookings.status`, `refunds`, `unit_holds` |
| Brokers | `agent_commissions`, `bookings.agent_id` FK |
| Finance dashboard | `cash_transactions`, `bank_accounts`, link `ledger` to source records |
| Project budget | `budget_categories`, `project_budgets`, category on POs |
| Investors | `investors`, `investor_contributions`, `investor_distributions` |
| Documents | `documents`, `demand_notice_log` |
| Operations | `grn`, `vendor_payments`, `inventory_items` / `stock_movements` |
| Admin | `users`, `audit_log`, `company_settings` |

---

## Open questions (need client answers)

1. **Cancellation** — refund rules, unit status, commission reversal?
2. **Investors** — profit share vs fixed return? Per project?
3. **Budget** — categories, who approves, tie to site logs?

---

*See `app.py` for API queries · `Todo.txt` for discovery notes*



xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx


* optional field
** ask sharjeel bhai (for now add these fields as dummy)


## Project: 
project name
project location
project description
area
city
start date
expected end date
status (planning, under construction, completed)
current progress
number of floors
number of units
project attributes:  [lift, parking, generator, park etc.....]
total area (ghaz)
estimated cost**


## Unit

Unit number  (standard such as JBV 102)
description*
project name
unit type (Flat, House, Shop)  
residential type (2 bed lounge, 2bed dd, 3bed dd)
Floor Number
Area(ghaz)
block/tower*
bedrooms*
bathrooms*
status (Available, Hold, Sold, Cancelled, Booked, Possession Delivered)
Base Sale price**
Final Sold price**
Booking Amount Required**
Furnishing Status: Builder condition, Semi Furnished, Fully furnished **/*
Unit Attributes: [Corner, Road Facing, Park Facing, pent house, near lift, near starecase, Roof Access]
additonal requirements: 
Possession Date*

## Customer

Customer name
father name
customer description*
residential address
CNIC
units
contact number
emergency contact number
email
total value to be paid
paid
outstanding
last payment
status (overdue, cleared, on track)

## Investor

Investor name
CNIC
mobile number
email
Investor Type (Monthly Return, Profit Sharing)*
Project*
Investment Amount
Investment Date
Monthly Return % *
Profit Share % *
Total Return Received
Outstanding Return
Status (Active, Completed, Withdrawn)
investor description


## Vendor/procurement

vendor name
description
contact
category
total payable
paid
balance
status


## Agent

vendor name
description
contact
category
total payable
paid
balance
status

## Booking
Booking Number
Customer
Unit
Agent *
Booking Date
Base Sale Price
Final Sale Price
Booking Amount
Installment Plan
Total Installments
Possession Date *
Status (Active, Completed, Cancelled)

## Installments

Booking number
Installment Number
Due Date
Amount
Type (Booking, Monthly, Quarterly, Possession)
Paid Amount
Remaining Amount
Payment Date *
Status (Pending, Paid, Partial, Overdue)

## Payment
Receipt Number
Customer
Booking
Installment *
Payment Date
Amount
Payment Method
Bank *
Reference Number *
Received By
Notes *

## Purchase Order
PO Number
Project*
Vendor
Category (Electrical, Paint, Plumbing)
Material 
Quantity
Unit Cost
Total Cost
Order Date
Expected Delivery Date *
Status (Ordered, Cancelled, Delivered, Closed**)   closed here means payment is done


## Site Log 

Project
Date
Reporter(Engineer / Supervisor)
Number of Workers
Work Done
Material Used
Issues / Delays *
Progress %
Remarks *
this site log will have dynamic and open fields

## Budget

Project
Budget Category
Planned Amount
Actual Spent
Variance
Status (Within Budget, Near Limit, Exceeded)