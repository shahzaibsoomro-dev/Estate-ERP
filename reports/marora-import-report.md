# Marora Residency — import test report

Source: `Maroara 120 V4.xlsx` · Company **Marora Residency** · admin `marora@havenbuilders.pk` / `Estate-Test-2026`

## Results vs the workbook

| Figure | Workbook | System | Why different |
|---|---:|---:|---|
| Total units | 11 | 11 |  |
| Sold units | 1 | 1 |  |
| Available units | 8 | 9 | Includes flat 201 (see Hold/Booked) |
| Hold/Booked units | 2 | 1 | Flat 201 cannot be 'Booked' without a customer and booking, so it stays Available |
| Total sales value | 5,670,000 | 5,670,000 |  |
| Collected from customers (flat 202) | 2,430,000 | 2,430,000 |  |
| Total collected incl. membership fee | 2,580,000 | 2,580,000 |  |
| Outstanding on flat 202 | 3,240,000 | 3,240,000 |  |
| Total expenses | 4,060,000 | 4,060,000 |  |
| Cash balance | 1,835,000 | 1,835,000 |  |
| Bank balance (workbook excludes partner capital) | -3,315,000 | -1,315,000 | The workbook's Bank Book leaves out the 2,000,000 partner capital that its own Cash Flow sheet includes |
| Cash + bank (workbook Cash Flow closing) | 520,000 | 520,000 |  |
| Partner capital | 2,000,000 | 2,000,000 |  |
| Net profit | 1,610,000 | 1,760,000 | System also counts the 150,000 membership fee as income; the workbook's P&L leaves it out |
| Vendor payables | 0 | 0 |  |
| Construction progress % | 15 | 15 |  |
| Balance sheet balances | OUT OF BALANCE | Balanced | The workbook's balance sheet does not balance; the system's does |
| Installments on flat 202 | 12 | 13 | 13th row added for the 320,000 the sheet never scheduled |
| Overdue installments (flat 202) | 2 | 2 |  |
| Overdue amount | 1,150,000 | 1,170,000 | Depends on today's date and how payments are allocated |

## Every step

Legend: ✅ accepted as expected · 🛑 rejected as expected (bad data or a validation test) · ❌ unexpected

| Sheet | Row | Step | Result | System message | Note |
|---|---|---|---|---|---|
| Setup | super admin | Sign in as superadmin@havenbuilders.pk | ✅ 200 |  |  |
| Setup | company | Create company 'Marora Residency' on the Growth plan with admin marora@havenbuilders.pk | ✅ 200 |  |  |
| Setup | admin | Admin signs in with the one-time password | ✅ 200 |  |  |
| Setup | admin | Admin is forced to change password before using the app | 🛑 403 | password_change_required |  |
| Setup | admin | Set password 'Marora-2026' (contains the email name 'marora') | 🛑 400 | Password needs must not contain your username | Password rule: must not contain the email username |
| Setup | admin | Set password 'Estate-Test-2026' | ✅ 200 |  |  |
| Setup | admin | Admin signs in with the new password | ✅ 200 |  |  |
| Setup | admin | Dashboard of the new company is empty | ✅ 200 |  | {'total_units': 0, 'sold': 0, 'available': 0, 'hold': 0, 'receivable': 0, 'payable': 0, 'collection_rate': 0, 'collected_total': 0, 'billed_total': 0} |
| 🏗️ Projects | row 4 | Create project PRJ-001 Marora Residency | ✅ 200 |  | Start date '15-01-2026' is text in the sheet; converted to 2026-01-15 |
| 🏗️ Projects | limit | Growth plan allows more than one project (probe; removed right after) | ✅ 200 |  |  |
| 🏗️ Projects | limit | Delete the probe project | ✅ 200 |  |  |
| 📋 Pay Plans | row 4 | Plan PLN-001 Monthly-18 (20% down + 18 monthly + 10% possession) | ✅  |  | The system keeps one active plan template per project; Monthly-18 is used by the flats |
| 📋 Pay Plans | row 5 | Plan PLN-002 Quarterly-12 (25% down + 12 quarterly + 10% possession) | ✅  |  | The system keeps one active plan template per project; Monthly-18 is used by the flats |
| 📋 Pay Plans | row 6 | Plan PLN-003 Half-Yearly-6 (30% down + 6 half-yearly + 10% possession) | ✅  |  | The system keeps one active plan template per project; Monthly-18 is used by the flats |
| 📋 Pay Plans | row 7 | Plan PLN-004 Milestone-5 (20% booking + 5 milestones + 20% possession) | ✅  |  | The system keeps one active plan template per project; Monthly-18 is used by the flats |
| 📋 Pay Plans | row 8 | Plan PLN-005 Cash-Full (Full cash (discount applicable)) | ✅  |  | The system keeps one active plan template per project; Monthly-18 is used by the flats |
| 📋 Pay Plans | PLN-001 | Save Monthly-18 as the project's plan: 20% down, 70% over 18 months, 10% at possession | ✅ 200 |  |  |
| 📋 Pay Plans | probe | Plan whose parts don't add up to 100% is rejected | 🛑 400 | Rule percentages must total exactly 100% of financed balance (got 70.00%) |  |
| 📋 Pay Plans | PLN-001 | Preview Monthly-18 on a 5,670,000 flat | ✅ 200 |  |  |
| 📋 Pay Plans | PLN-001 | Preview installments + down payment = sale price | ✅  |  | 19 installments totalling 4,536,000 |
| Budget | Land / plot | Create budget category 'Land / plot' | ✅ 200 |  |  |
| Budget | Material | Create budget category 'Material' | ✅ 200 |  |  |
| Budget | Labor | Create budget category 'Labor' | ✅ 200 |  |  |
| Budget | Contractor | Create budget category 'Contractor' | ✅ 200 |  |  |
| Budget | Admin | Create budget category 'Admin' | ✅ 200 |  |  |
| Budget | Marketing | Create budget category 'Marketing' | ✅ 200 |  |  |
| Budget | Other | Create budget category 'Other' | ✅ 200 |  |  |
| Budget | PRJ-001 | Budget line: overall 250,000,000 | ✅ 200 |  |  |
| 🏘️ Flat Register | row 8 | Create flat 1 (Ground, 468 sqft, 3,510,000) | ✅ 200 |  |  |
| 🏘️ Flat Register | row 9 | Create flat 2 (Ground, 702 sqft, 5,265,000) | ✅ 200 |  |  |
| 🏘️ Flat Register | row 10 | Create flat 101 (1st, 522 sqft, 3,915,000) | ✅ 200 |  |  |
| 🏘️ Flat Register | row 11 | Create flat 102 (1st, 756 sqft, 5,670,000) | ✅ 200 |  |  |
| 🏘️ Flat Register | row 12 | Create flat 201 (2nd, 522 sqft, 3,915,000) | ✅ 200 |  |  |
| 🏘️ Flat Register | row 13 | Create flat 202 (2nd, 756 sqft, 5,670,000) | ✅ 200 |  |  |
| 🏘️ Flat Register | row 14 | Create flat 301 (3rd, 522 sqft, 3,915,000) | ✅ 200 |  |  |
| 🏘️ Flat Register | row 15 | Create flat 302 (3rd, 756 sqft, 5,670,000) | ✅ 200 |  |  |
| 🏘️ Flat Register | row 16 | Create flat 401 (4th, 522 sqft, 3,915,000) | ✅ 200 |  |  |
| 🏘️ Flat Register | row 17 | Create flat 402 (4th, 756 sqft, 5,670,000) | ✅ 200 |  |  |
| 🏘️ Flat Register | row 18 | Create flat 500 (5th, 1278 sqft, 9,710,000) | ✅ 200 |  |  |
| 🏘️ Flat Register | probe | Creating flat 202 a second time is rejected | 🛑 400 | Unit number already exists in this project |  |
| 👤 Customers | row 5 | Register customer C-001 Zulfiqar Ali Sapro (CNIC 42101-1234567-1) | ✅ 200 |  |  |
| 👤 Customers | row 6 | Register customer C-002 Sharjeel (CNIC 42101-1234567-1) | 🛑 400 | CNIC already exists | Same CNIC as C-001 — CNIC must be unique |
| 👤 Customers | row 7 | Register customer C-003 hello (CNIC 42101-1234567-1) | 🛑 400 | CNIC already exists | Same CNIC as C-001 — CNIC must be unique |
| 👤 Customers | row 8 | Register customer C-004 aiman (CNIC 42101-1234567-1) | 🛑 400 | CNIC already exists | Same CNIC as C-001 — CNIC must be unique |
| 👤 Customers | probe | Customer without CNIC is rejected | 🛑 422 | cnic: Field required |  |
| 🏘️ Flat Register | row 13 | Book flat 202 to C-001 on 2026-04-15 for 5,670,000 with the 12-row schedule totalling 5,350,000 | 🛑 400 | Payment plan totals PKR 5,350,000 but the sale price is PKR 5,670,000 (short by PKR 320,000) | Schedule is 320,000 short of the sale price |
| 🏘️ Flat Register | row 13 | Book flat 202 again with a 13th row of 320,000 due at possession for the unscheduled balance | ✅ 200 |  |  |
| 🏘️ Flat Register | probe | Booking flat 202 a second time is rejected | 🛑 400 | Unit is not available for booking (status: booked) |  |
| 🏘️ Flat Register | row 9 | Put flat 2 on hold without a customer (Flat Register says Hold) | ✅ 200 |  |  |
| 🏘️ Flat Register | row 12 | Mark flat 201 'Booked' with no customer and no booking | 🛑 400 | A unit becomes booked or sold only through a booking — create the booking instead | Booked/Sold only comes from a real booking, so flat 201 stays Available |
| 🏘️ Flat Register | probe | Creating a new flat directly as 'sold' is rejected | 🛑 400 | New units start as available — use a hold or booking to change that |  |
| 🏘️ Flat Register | flat 1 | Flat 1 is 'Available' but lists customer C-003 — left available (no booking) | ✅  |  | Customer could not be registered (duplicate CNIC) |
| 🏘️ Flat Register | flat 101 | Flat 101 is 'Available' but lists customer C-002 — left available (no booking) | ✅  |  | Customer could not be registered (duplicate CNIC) |
| 🏘️ Flat Register | flat 401 | Flat 401 is 'Available' but lists customer C-004 — left available (no booking) | ✅  |  | Customer could not be registered (duplicate CNIC) |
| 🏘️ Flat Register | flat 500 | Flat 500 is 'Available' but lists customer C-004 — left available (no booking) | ✅  |  | Customer could not be registered (duplicate CNIC) |
| 📋 Booking Register | row 5 | BK-302: flat 302 to C-001 on 2023-01-01 00:00:00 (Monthly-11) | ✅  |  | Not imported: Flat Register shows this flat Available and the workbook's totals exclude it |
| 📋 Booking Register | row 6 | BK-401: flat 401 to C-002 on 2023-01-01 00:00:00 (Monthly-11) | ✅  |  | Not imported: Flat Register shows this flat Available and the workbook's totals exclude it |
| 💳 PAYMENTS Entery | row 11 | RCP-001: 385,000 Bank Transfer on 2026-05-15 against F-202-01 | ✅ 200 |  |  |
| 💳 PAYMENTS Entery | row 12 | R-002: 1,190,000 Cash on 2026-06-15 against F-202-01 | ✅ 200 |  |  |
| 💳 PAYMENTS Entery | row 13 | R-003: 150,000 Cash on 2026-07-15 against F-202-01 | ✅ 200 |  |  |
| 💳 PAYMENTS Entery | row 14 | R-004: 275,000 Cash on 2026-08-15 against F-202-01 | ✅ 200 |  |  |
| 💳 PAYMENTS Entery | row 15 | R-005: 280,000 Cash on 2026-09-15 against F-202-02 | 🛑 400 | Payment exceeds remaining installment amount | 280,000 against F-202-02 whose amount is 150,000 |
| 💳 PAYMENTS Entery | row 15 | R-005 again without a fixed installment (system allocates oldest-first) | ✅ 200 |  |  |
| 💳 PAYMENTS Entery | row 16 | R-006: 150,000 Online Transfer on (no date) | ✅ 200 |  | No date on the sheet — the system dates it today |
| 💳 PAYMENTS Entery | row 17 | Membership fee 150,000 with no date | 🛑 422 | entry_date: Field required | Date is required |
| 💳 PAYMENTS Entery | row 17 | Membership fee 150,000 into bank, dated 2026-09-16 (import date) | ✅ 200 |  | No customer on the sheet, so it goes to the cashbook |
| 💳 PAYMENTS Entery | probe | Zero payment is rejected | 🛑 400 | Amount must be greater than 0 |  |
| 💳 PAYMENTS Entery | probe | Negative payment is rejected | 🛑 400 | Amount must be greater than 0 |  |
| 💳 PAYMENTS Entery | probe | Payment larger than the whole outstanding balance is rejected | 🛑 400 | Payment exceeds the booking's outstanding balance (PKR 3,240,000) |  |
| 💳 PAYMENTS Entery | probe | Payment dated years in the future is rejected | 🛑 400 | Payment date cannot be in the future — record post-dated cheques when they clear |  |
| 💳 PAYMENTS Entery | probe | Payment date in dd-mm-yyyy text is rejected | 🛑 400 | Payment date must be YYYY-MM-DD |  |
| 💳 PAYMENTS Entery | probe | Payment on a booking that doesn't exist is rejected | 🛑 400 | Booking not found |  |
| 👥 Partners | row 8 | Partner P-002 sharjeel ahmed: capital 1,000,000, 50% share | ✅ 200 |  |  |
| 👥 Partners | row 9 | Partner P-003 Faraz Gulzar: capital 1,000,000, 50% share | 🛑 400 | Another partner already has CNIC 42101-0000002-2 | Same CNIC 42101-0000002-2 as P-002 in the sheet |
| 👥 Partners | row 9 | Partner P-003 again with CNIC left blank | ✅ 200 |  |  |
| 👥 Partners | row 15 | PC-001: 1,000,000 capital from P-002 on 2026-05-14 | ✅ 200 |  | Contribution dated a day before the partner's join date |
| 👥 Partners | row 16 | PC-002: 1,000,000 capital from P-003 on 2026-05-14 | ✅ 200 |  | Contribution dated a day before the partner's join date |
| 🏪 Vendors | row 4 | Vendor V-001 Mansoor Ali (cement and Blocks, NTN 1234567-8) | ✅ 200 |  |  |
| 🏪 Vendors | row 5 | Vendor V-002 Saeed khan (Steel, NTN 8765432-1) | ✅ 200 |  |  |
| 🏪 Vendors | row 6 | Vendor V-003 Gul Zaib khan (Hardware, NTN 5678901-2) | ✅ 200 |  |  |
| 🏪 Vendors | row 7 | Vendor V-004 Dawood Jan (Raay / Bajri, NTN 5678901-2) | 🛑 400 | Another vendor already has NTN 5678901-2 | Same NTN, contact and email as V-003 |
| 🏪 Vendors | row 7 | Vendor V-004 again with NTN left blank | ✅ 200 |  |  |
| 📦 Materials | row 4 | Material M-001 OPC Cement 50kg (Bag @ 1,000) | ✅ 200 |  |  |
| 📦 Materials | row 5 | Material M-002 Steel Rebar 12mm (Tonne @ 180,000) | ✅ 200 |  |  |
| 📦 Materials | row 6 | Material M-003 Bricks Standard (1000 pcs @ 12,000) | ✅ 200 |  |  |
| 📦 Materials | row 7 | Material M-004 SRC Cement (1000 pcs @ 15,000) | ✅ 200 |  | Cement priced per '1000 pcs' |
| 📦 PURCHASES ← Enter Here | row 6 | PO-001: OPC Cement 50kg × 0 = 0 | 🛑 400 | Total must be greater than 0 | Quantity is 0, so the order is worth nothing |
| 📦 PURCHASES ← Enter Here | row 7 | PO-002: Steel Rebar 12mm × 0 = 0 | 🛑 400 | Total must be greater than 0 | Quantity is 0, so the order is worth nothing |
| 📦 PURCHASES ← Enter Here | row 8 | PO-003: SRC Cement × 0 = 0 | 🛑 400 | Total must be greater than 0 | Quantity is 0, so the order is worth nothing |
| 📦 PURCHASES ← Enter Here | probe | Purchase order with negative quantity is rejected | 🛑 400 | Total must be greater than 0 |  |
| 📦 PURCHASES ← Enter Here | probe | Vendor payment of 0 is rejected | 🛑 400 | Amount must be greater than 0 |  |
| 👷 Contractors | row 4 | Contractor CON-001 Muhammad Arif (Civil Works) | ✅ 200 |  |  |
| 👷 Contractors | row 5 | Contractor CON-002 Afzal (Electrical) | ✅ 200 |  |  |
| 🏗️ Site Log | row 4 | Assign CON-001 to the project for Foundation Work | ✅ 200 |  |  |
| 🏗️ Site Log | row 4 | Site log 2026-05-01: Foundation Complete, progress 15% | ✅ 200 |  |  |
| 🏗️ Site Log | probe | Contractor bill/payment of 0 is rejected | 🛑 400 | Amount must be greater than 0 |  |
| 🧾 EXPENSES ← Enter Here | row 11 | PV-001: 2,000,000 Asset paid from HBL | ✅ 200 |  |  |
| 🧾 EXPENSES ← Enter Here | row 12 | PV-002: 2,000,000 Asset paid from HBL | ✅ 200 |  | Identical to PV-001 (same date, payee, amount and cheque CHQ-5001) — likely a duplicate |
| 🧾 EXPENSES ← Enter Here | row 13 | PV-003: 60,000 Commission paid from Cash | ✅ 200 |  | No project in the sheet — company-wide |
| 🧾 EXPENSES ← Enter Here | probe | Expense dated in dd-mm-yyyy text is rejected | 🛑 400 | Date must be YYYY-MM-DD |  |
| 🧾 EXPENSES ← Enter Here | probe | Expense of 0 is rejected | 🛑 400 | Amount must be greater than 0 |  |
| 🧾 EXPENSES ← Enter Here | probe | Expense paid from an unknown account is rejected | 🛑 400 | Paid from must be Cash or Bank |  |

## Flat 202 schedule after import

| # | Type | Due | Amount | Paid | Remaining | Status |
|---|---|---|---:|---:|---:|---|
| 1 | Advance | 2026-06-01 | 2,000,000 | 2,000,000 | 0 | paid |
| 2 | Monthly | 2026-04-01 | 150,000 | 150,000 | 0 | paid |
| 3 | Monthly | 2026-06-01 | 150,000 | 150,000 | 0 | paid |
| 4 | Quarterly | 2026-07-01 | 1,000,000 | 130,000 | 870,000 | partial |
| 5 | Quarterly | 2026-08-01 | 150,000 | 0 | 150,000 | overdue |
| 6 | Quarterly | 2026-09-01 | 150,000 | 0 | 150,000 | overdue |
| 7 | Quarterly | 2026-10-01 | 1,000,000 | 0 | 1,000,000 | pending |
| 8 | Quarterly | 2026-11-01 | 150,000 | 0 | 150,000 | pending |
| 9 | Quarterly | 2026-12-01 | 150,000 | 0 | 150,000 | pending |
| 10 | Quarterly | 2027-01-01 | 150,000 | 0 | 150,000 | pending |
| 11 | Quarterly | 2027-02-01 | 150,000 | 0 | 150,000 | pending |
| 12 | Quarterly | 2027-03-01 | 150,000 | 0 | 150,000 | pending |
| 13 | Balance (not scheduled in sheet) | 2027-12-31 | 320,000 | 0 | 320,000 | pending |

## Audit checks on the new company

- ✅ Every journal entry balances (debits = credits) — 13 entries checked
- ⚠️ Cash and bank balances are not negative — Negative: Bank accounts — payments recorded without matching receipts
- ✅ No budget line is over budget — OK
- ✅ No installment is paid more than its amount — OK
- ✅ Cancelled bookings have no open installments — OK
- ✅ No payments dated after a booking was cancelled — OK
- ✅ Every customer payment has a receipt — OK
