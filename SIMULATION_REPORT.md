# Gulberg Square simulation report

Ran against `http://127.0.0.1:5051` on 2026-08-09. Backup: `db/haven.pre-sim.db` (exists).

## 1. Wipe / keep / create

- Kept Haven projects: **3** (ids [1, 2, 3]). Haven units/bookings/customer receipts untouched.
- After wipe: projects=3, units=280, customers=44, bookings=45, vendors/agents/investors=0.
- Haven customer receipts still in cashbook: PKR 44,080,000.
- Created **Gulberg Square** (id 66): 8 shops + 24 flats + 2 penthouses = 34 units; 2 holds; 14 customers; 3 agents; 5 vendors; 3 investors; 4 budget lines.

## 2. Narrative

- 2025-01-15  Gulberg Square onboarded: 34 units, 2 holds (GS-204, GS-G08)
- 2025-02-01  Investor capital in: Khawaja 15M, Crescent 20M, Metro 15M
- 2025-02-10  Bilal Ahmed booked GS-G01 for PKR 22,000,000 (DP 2,200,000) direct
- 2025-02-12  Hina Qureshi booked GS-101 for PKR 18,000,000 (DP 2,000,000) via malik
- 2025-02-15  Usman Tariq booked GS-203 for PKR 28,500,000 (DP 2,000,000) via horizon
- 2025-02-20  Saima Riaz booked GS-G03 for PKR 25,000,000 (DP 1,500,000) via malik
- 2025-02-25  Nadia Sheikh booked GS-102 for PKR 18,000,000 (DP 2,000,000) via horizon
- 2025-03-01  Omar Farooq booked GS-104 for PKR 18,200,000 (DP 2,000,000) via citylink
- 2025-03-05  Farah Malik booked GS-301 for PKR 29,000,000 (DP 3,000,000) via malik
- 2025-03-10  Imran Cheema booked GS-PH1 for PKR 55,000,000 (DP 8,000,000) via horizon
- 2025-03-12  Rabia Noor booked GS-G05 for PKR 30,000,000 (DP 12,000,000) direct
- 2025-05-01  Cancelled Nadia Sheikh GS-102  paid=4666666 forfeit=600000 refund=4066666 (not posted to cashbook)
- 2025-05-05  Kamal Hussain booked GS-102 for PKR 18,000,000 (DP 2,000,000) via malik
- 2025-07-08  Omar Farooq caught up missed installments in one transfer
- 2025-07-20  GS-301 transferred Farah Malik -> Zainab Ali
- 2025-08-01  Cancelled draft paint PO 1M (budget should ignore it)
- 2026-01-20  Possession delivered GS-G01 Bilal Ahmed
- 2026-03-15  Possession delivered GS-PH1 while still owing
- 2026-08  Simulation clock stops near today. Saima still chronic overdue.
- Saima Riaz (GS-G03): tiny token payment only — chronic overdue for Recovery/Demand.
- Usman Tariq: half-pays + one unallocated 300k cash (no installment id) — schedule vs cash disagree.
- City Link Associates set inactive after Omar's booking commission existed.

## 3. Expected vs actual

**30/30 checks passed.**

| Check | Result | Expected | Actual | Notes |
|---|---|---|---|---|
| gulberg live unit count | PASS | 34 | 34 |  |
| project.number_of_units stored | PASS | 34 | 34 | planning field; live count also returned as total_units |
| dashboard gulberg total_units | PASS | 34 | 34 |  |
| dashboard gulberg hold | PASS | 2 | 2 |  |
| site progress last write | PASS | 72 | 72 |  |
| cancelled installments stay cancelled after dashboard refresh | PASS | True | True | statuses=[{'status': 'cancelled', 'n': 10}, {'status': 'paid', 'n': 3}] |
| transfer booking owner is Zainab | PASS | 153 | 153 |  |
| transfer: Farah has no payment rows on moved booking | PASS | 0 | 0 |  |
| transfer: Zainab owns payment rows | PASS | True | True | zainab_paid=29000000 |
| cashbook inflow (company-wide) | PASS | 325684322 | 325684322 | includes leftover Haven customer receipts |
| cashbook outflow | PASS | 26593750 | 26593750 |  |
| dashboard payable == vendor balances + agent unpaid | PASS | 2966750 | 2966750 | vendor_bal=1650000 agent_unpaid=1316750 |
| agent unpaid excludes reversed commissions | PASS | 1316750 | 1316750 | reversed_rows=1 |
| budget finishing actual excludes cancelled 1M paint PO | PASS | 3000000 | 3000000 |  |
| structural budget Exceeded | PASS | Exceeded | Exceeded |  |
| electrical budget Near Limit | PASS | True | True | Near Limit |
| plumbing budget Exceeded | PASS | Exceeded | Exceeded |  |
| khawaja contributed | PASS | 15000000 | 15000000 |  |
| crescent contributed | PASS | 40000000 | 40000000 |  |
| khawaja agreed | PASS | 25000000 | 25000000 |  |
| unallocated payment reflected consistently | PASS | True | True |  |
| possessed unit display delivered/possession | PASS | True | True |  |
| double-book blocked | PASS | True | True |  |
| overpay blocked | PASS | True | True |  |
| delete investor with money blocked | PASS | True | True |  |
| portal lists Bilal (active booking) | PASS | True | True |  |
| portal detail for Bilal | PASS | True | True |  |
| Saima appears on Gulberg overdue/recovery | PASS | True | True |  |
| sales report includes Gulberg Square | PASS | True | True |  |
| audit has booking/payment activity | PASS | True | True |  |

### Snapshot

- Gulberg inventory: 34 total / 23 available / 2 hold / 7 booked / 2 delivered. Progress 72%.
- Cashbook in PKR 325,684,322 / out PKR 26,593,750 / net PKR 299,090,572.
- Vendor payable PKR 21,800,000 paid PKR 20,150,000 balance PKR 1,650,000. Agent unpaid PKR 1,316,750. Dashboard payable PKR 2,966,750.
- Gulberg receivable (dashboard filter) PKR 36,862,344.
- Ageing report: `{'d30': 1870000, 'd60': 0, 'd90': 87262344, 'items': 71}`.
- Transfer paid rows: Farah PKR 0 vs Zainab PKR 29,000,000 (API paid PKR 29,000,000, outstanding PKR 0).
- Nadia installment statuses after refresh: `[{'status': 'cancelled', 'n': 10}, {'status': 'paid', 'n': 3}]`.
- Negative tests: `{"double_book": "blocked HTTP 400", "overpay": "blocked HTTP 400", "cancel_paid_po": "blocked HTTP 400", "poss_bilal": "ok", "poss_imran_owing": "ALLOWED (no outstanding check)", "del_investor_money": "blocked HTTP 400", "del_proj_sitelog": "blocked HTTP 400: Cannot delete project \u2014 1 site log(s). Remove them first."}`.
- Cancel preview/result: `{'booking_id': 80, 'booking_no': 'BK-1066', 'unit_id': 440, 'total_paid': 4666666, 'forfeit_pct': 30.0, 'forfeit_amount': 600000, 'refund_amount': 4066666}` / `{'ok': True, 'booking_id': 80, 'total_paid': 4666666, 'forfeit_amount': 600000, 'refund_amount': 4066666, 'forfeit_pct': 30.0}`.

## 4. Data mapping / calculation / fit

- **LOW** `possession` — Booking stays status=active after possession_delivered. Realistic ops usually mark completed.
- **MED** `possession` — Possession allowed on GS-PH1 while installments still outstanding.
- **MED** `cancel` — Cancel computed refund 4066666 but no cashbook/ledger outflow was posted.

Haven seed quirks left untouched: Commercial Hub all `sold` without bookings; some Residencia units `booked` without rows.

## 5. UX / functionality

- **MED** _Accounts_ — Cashbook is company-wide (now labelled in UI). Dashboard project filter will not match Accounts net cash.
- **LOW** _Demand notices_ — Preview is honest now; WhatsApp/email/PDF still not connected. late_fee_pct setting unused.
- **LOW** _Activity_ — Audit still omits most CRUD and site logs (payments/bookings/money are logged).

## 6. Fixes applied this pass

- Cancelled installments no longer resurrected by `refresh_statuses`.
- Transfer moves `payments.customer_id` and accepts `transfer_date`.
- Dashboard payable matches vendor balances + non-reversed agent unpaid.
- Budget actual excludes cancelled POs; booking/receipt numbers use max suffix.
- Unallocated customer payments apply FIFO to installments.
- `delete_project` returns 400 when site logs exist.
- UX: Hold/Release, pay date/method, possession date + outstanding warn, cancel reason, booking confirm, project budget table, ageing line items, honest demand preview, Accounts labelled company-wide.

## 7. Still open / product choices

- Cancel refund is computed but not posted to cashbook.
- Possession allowed while outstanding; booking stays `active` (so portal still lists them).
- Cashbook has no project filter.
- Demand WhatsApp/PDF/email not built. Multi-agreement investors not in UI.
- Haven seed: Commercial Hub sold without bookings; leftover verify customers on Heights.

Replay: `python -m backend.simulate wipe && python -m backend.simulate run`  
Re-check after fixes: `python -m backend.simulate assert`
