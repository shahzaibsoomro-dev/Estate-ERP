"""Initialize and seed the v2 database."""
import json
import os
import sqlite3

from backend.config import DB_PATH, DEFAULT_SETTINGS, SCHEMA_PATH, SCHEMA_VERSION

_DIR = os.path.dirname(__file__)


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def needs_init() -> bool:
    if not os.path.exists(DB_PATH) or os.path.getsize(DB_PATH) < 500:
        return True
    try:
        conn = _connect()
        row = conn.execute(
            "SELECT value FROM schema_meta WHERE key='version'"
        ).fetchone()
        conn.close()
        return not row or int(row[0]) != SCHEMA_VERSION
    except sqlite3.Error:
        return True


def init_schema(conn: sqlite3.Connection) -> None:
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.execute(
        "INSERT OR REPLACE INTO schema_meta(key, value) VALUES('version', ?)",
        (str(SCHEMA_VERSION),),
    )


def seed_settings(conn: sqlite3.Connection) -> None:
    for key, value in DEFAULT_SETTINGS.items():
        conn.execute(
            "INSERT OR REPLACE INTO company_settings(key, value) VALUES(?, ?)",
            (key, value),
        )


def run_seed(conn: sqlite3.Connection) -> None:
    """Populate sample data."""
    seed_settings(conn)

    projects = [
        (
            "Haven Heights – Block A", "Bahria Town, Lahore",
            "Premium residential block", "Bahria Town", "Lahore",
            "2023-01-15", "2025-12-31", "under_construction", 72, 15, 120,
            json.dumps(["lift", "parking", "generator", "park"]), 5000.0, 850000000,
        ),
        (
            "Haven Residencia – Phase 2", "DHA Phase 6, Karachi",
            "Luxury apartments", "DHA Phase 6", "Karachi",
            "2024-07-01", "2026-06-30", "under_construction", 45, 12, 96,
            json.dumps(["lift", "parking", "security"]), 4200.0, 720000000,
        ),
        (
            "Haven Commercial Hub", "Blue Area, Islamabad",
            "Commercial shops", "Blue Area", "Islamabad",
            "2022-03-01", "2024-03-31", "completed", 100, 8, 64,
            json.dumps(["parking", "elevator"]), 2800.0, 480000000,
        ),
    ]
    conn.executemany(
        """INSERT INTO projects(name, location, description, area, city,
           start_date, expected_end_date, status, current_progress,
           number_of_floors, number_of_units, project_attributes,
           total_area_ghaz, estimated_cost) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        projects,
    )

    customers = [
        ("Ahmed Raza", "Zubair Raza", None, "House 12, Model Town, Lahore",
         "35202-1234567-9", "0321-1234567", "0321-9999999", "ahmed.raza@gmail.com"),
        ("Sara Khan", "Ali Khan", None, "Flat 5, Gulberg III, Lahore",
         "42201-9876543-2", "0333-9876543", "0333-1111111", "sara.khan@yahoo.com"),
        ("Fahad Siddiqui", "Amna Siddiqui", None, "Plot 22, DHA Karachi",
         "61101-5556789-1", "0301-5556789", "0301-2222222", "fahad.s@gmail.com"),
        ("Nadia Malik", "Tariq Malik", None, "House 7, F-7/3, Islamabad",
         "35501-4441234-8", "0315-4441234", "0315-3333333", "nadia.malik@hotmail.com"),
        ("Kamran Ali", "Aamir Ali", None, "Flat 3B, Askari 10, Lahore",
         "36302-7778899-5", "0312-7778899", "0312-4444444", "kamran.ali@gmail.com"),
        ("Imran Butt", "Asma Butt", None, "House 90, Johar Town, Lahore",
         "35203-8881234-6", "0345-8881234", "0345-5555555", "imran.butt@gmail.com"),
        ("Farhan Iqbal", "Sobia Iqbal", None, "Flat 12, F-11 Markaz, Islamabad",
         "42301-6662211-3", "0311-6662211", "0311-6666666", "farhan.iqbal@gmail.com"),
    ]
    conn.executemany(
        """INSERT INTO customers(name, father_name, description, residential_address,
           cnic, contact_number, emergency_contact_number, email) VALUES(?,?,?,?,?,?,?,?)""",
        customers,
    )

    agents = [
        ("Tariq Associates", "Broker – Heights A", "0321-1112222", 2.0, "active"),
        ("Raza Realty", "Broker – Residencia", "0333-2223333", 2.5, "active"),
        ("Ali Kamran", "Independent agent", "0301-3334444", 1.5, "active"),
    ]
    conn.executemany(
        "INSERT INTO agents(name, description, contact, default_rate_pct, status) VALUES(?,?,?,?,?)",
        agents,
    )

    types = ["2 Bed", "3 Bed", "2 Bed", "Shop", "2 Bed", "3 Bed", "2 Bed", "2 Bed"]
    sizes = [1200, 1650, 1200, 450, 1200, 1650, 1100, 1200]
    prices = [8500000, 11500000, 8500000, 3500000, 8200000, 11000000, 7800000, 8500000]
    facings = ["East", "West", "North", "South", "East", "West", "Park View", "Main Road"]

    unit_rows = []
    for proj_id, prefix, total in [(1, "A", 120), (2, "B", 96), (3, "C", 64)]:
        for i in range(1, total + 1):
            floor = ((i - 1) // 8) + 1
            tidx = (i - 1) % len(types)
            if proj_id == 3:
                status = "sold"
            elif i <= int(total * 0.667):
                status = "booked" if i <= 7 else "sold"
            elif i <= int(total * 0.667) + int(total * 0.079):
                status = "hold"
            else:
                status = "available"
            utype = "Shop" if tidx == 3 else types[tidx]
            unit_rows.append((
                proj_id, f"{prefix}-{i:03d}", None, utype, utype,
                floor, sizes[tidx] / 10, None, None, None, status,
                prices[tidx], None, prices[tidx] // 3, "Builder condition",
                json.dumps([facings[tidx % len(facings)]]), None, None,
                None, None, None,
            ))

    conn.executemany(
        """INSERT INTO units(project_id, unit_no, description, unit_type, residential_type,
           floor_number, area_ghaz, block_tower, bedrooms, bathrooms, status,
           base_sale_price, final_sold_price, booking_amount_required, furnishing_status,
           unit_attributes, additional_requirements, possession_date,
           hold_customer_id, hold_until, hold_notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        unit_rows,
    )

    bookings = [
        ("BK-1001", 1, 1, 1, 1, "2025-01-15", 8500000, 8500000, 2500000, "2025-12-31", "active", "Cheque"),
        ("BK-1002", 2, 2, 1, 1, "2024-11-01", 8500000, 8500000, 2500000, "2025-12-31", "active", "Bank Transfer"),
        ("BK-1003", 3, 3, 1, None, "2024-08-10", 11500000, 11500000, 4000000, "2025-12-31", "active", "Cheque"),
        ("BK-1004", 4, 4, 1, 2, "2024-09-20", 8200000, 8200000, 2000000, "2025-12-31", "active", "Cash"),
        ("BK-1005", 5, 5, 1, None, "2024-10-05", 8500000, 8500000, 3000000, "2025-12-31", "active", "Cheque"),
        ("BK-1006", 6, 6, 1, 1, "2024-07-01", 8500000, 8500000, 2500000, "2025-12-31", "active", "Bank Transfer"),
        ("BK-1007", 7, 7, 1, None, "2024-12-01", 8500000, 8500000, 2500000, "2025-12-31", "active", "Cheque"),
    ]
    conn.executemany(
        """INSERT INTO bookings(booking_no, customer_id, unit_id, project_id, agent_id,
           booking_date, base_sale_price, final_sale_price, booking_amount,
           possession_date, status, payment_mode) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        bookings,
    )

    for uid in range(1, 8):
        conn.execute("UPDATE units SET status='booked' WHERE id=?", (uid,))

    plans = [
        (1, 1, 1, [
            (2500000, "2025-01-15", "Booking", "Down payment", 2500000, 0, "paid"),
            (500000, "2025-02-15", "Monthly", "Feb", 500000, 0, "paid"),
            (500000, "2025-03-15", "Monthly", "Mar", 0, 500000, "overdue"),
            (500000, "2025-04-15", "Monthly", "Apr", 0, 500000, "overdue"),
            (500000, "2025-05-15", "Monthly", "May", 0, 500000, "pending"),
            (1000000, "2025-09-01", "Stage", "Slab Floor 3", 0, 1000000, "pending"),
            (1000000, "2025-12-01", "Possession", "On possession", 0, 1000000, "pending"),
        ]),
        (2, 2, 2, [
            (2500000, "2024-11-01", "Booking", "Down payment", 2500000, 0, "paid"),
            (500000, "2024-12-01", "Monthly", "Dec", 500000, 0, "paid"),
            (500000, "2025-01-15", "Monthly", "Jan", 500000, 0, "paid"),
            (500000, "2025-02-15", "Monthly", "Feb", 500000, 0, "paid"),
            (500000, "2025-03-15", "Monthly", "Mar", 500000, 0, "paid"),
            (500000, "2025-04-01", "Monthly", "Apr", 0, 500000, "overdue"),
            (500000, "2025-05-01", "Monthly", "May", 0, 500000, "pending"),
        ]),
        (3, 3, 3, [
            (4000000, "2024-08-10", "Booking", "Down payment", 4000000, 0, "paid"),
            (700000, "2024-09-10", "Monthly", "Sep", 700000, 0, "paid"),
            (700000, "2024-10-10", "Monthly", "Oct", 700000, 0, "paid"),
            (700000, "2024-11-10", "Monthly", "Nov", 700000, 0, "paid"),
            (700000, "2024-12-10", "Monthly", "Dec", 700000, 0, "paid"),
            (700000, "2025-01-10", "Monthly", "Jan", 700000, 0, "paid"),
            (700000, "2025-02-10", "Monthly", "Feb", 700000, 0, "paid"),
            (700000, "2025-03-10", "Monthly", "Mar", 700000, 0, "paid"),
            (700000, "2025-04-10", "Monthly", "Apr", 700000, 0, "paid"),
        ]),
        (4, 4, 4, [
            (2000000, "2024-09-20", "Booking", "Down payment", 2000000, 0, "paid"),
            (620000, "2024-10-20", "Monthly", "Oct", 620000, 0, "paid"),
            (620000, "2024-11-20", "Monthly", "Nov", 620000, 0, "paid"),
            (620000, "2024-12-20", "Monthly", "Dec", 0, 620000, "overdue"),
            (620000, "2025-01-20", "Monthly", "Jan", 0, 620000, "overdue"),
            (620000, "2025-02-20", "Monthly", "Feb", 0, 620000, "pending"),
        ]),
        (5, 5, 5, [
            (3000000, "2024-10-05", "Booking", "Down payment", 3000000, 0, "paid"),
            (550000, "2024-11-05", "Monthly", "Nov", 550000, 0, "paid"),
            (550000, "2024-12-05", "Monthly", "Dec", 550000, 0, "paid"),
            (550000, "2025-01-05", "Monthly", "Jan", 550000, 0, "paid"),
            (550000, "2025-02-05", "Monthly", "Feb", 0, 550000, "pending"),
        ]),
        (6, 6, 6, [
            (2500000, "2024-07-01", "Booking", "Down payment", 2500000, 0, "paid"),
            (480000, "2024-08-01", "Monthly", "Aug", 480000, 0, "paid"),
            (480000, "2024-09-01", "Monthly", "Sep", 480000, 0, "paid"),
            (480000, "2024-10-01", "Monthly", "Oct", 480000, 0, "paid"),
            (480000, "2024-11-01", "Monthly", "Nov", 0, 480000, "overdue"),
            (480000, "2024-12-01", "Monthly", "Dec", 0, 480000, "overdue"),
            (480000, "2025-01-01", "Monthly", "Jan", 0, 480000, "pending"),
        ]),
        (7, 7, 7, [
            (2500000, "2024-12-01", "Booking", "Down payment", 2500000, 0, "paid"),
            (600000, "2025-01-01", "Monthly", "Jan", 600000, 0, "paid"),
            (600000, "2025-02-01", "Monthly", "Feb", 0, 600000, "overdue"),
            (600000, "2025-03-01", "Monthly", "Mar", 0, 600000, "pending"),
        ]),
    ]

    inst_id = 1
    pay_id = 1
    for bk_id, cust_id, unit_id, rows in plans:
        for n, (amt, due, itype, notes, paid, remaining, status) in enumerate(rows, 1):
            conn.execute(
                """INSERT INTO installments(id, booking_id, customer_id, unit_id,
                   installment_no, due_date, amount, paid_amount, remaining_amount,
                   type, notes, status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (inst_id, bk_id, cust_id, unit_id, n, due, amt, paid, remaining, itype, notes, status),
            )
            if paid > 0 and paid >= amt:
                conn.execute(
                    """INSERT INTO payments(id, customer_id, booking_id, installment_id,
                       amount, payment_date, payment_method, received_by)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (pay_id, cust_id, bk_id, inst_id, amt, due, "Cheque", "Admin"),
                )
                conn.execute(
                    "INSERT INTO receipts(payment_id, receipt_no) VALUES(?, ?)",
                    (pay_id, f"RCP-{1000 + pay_id}"),
                )
                pay_id += 1
            inst_id += 1

    commissions = [
        (1, 1, 2.0, 170000),
        (2, 1, 2.0, 170000),
        (4, 2, 2.5, 205000),
        (6, 1, 2.0, 170000),
    ]
    for bk_id, ag_id, rate, amt in commissions:
        conn.execute(
            """INSERT INTO agent_commissions(booking_id, agent_id, rate_pct,
               commission_amount, paid_amount, status) VALUES(?,?,?,?,?,?)""",
            (bk_id, ag_id, rate, amt, amt if bk_id != 4 else 0, "paid" if bk_id != 4 else "earned"),
        )

    vendors = [
        ("Steel Corp Ltd", "Structural steel supplier", "0321-1110001", "Structural Steel", "active"),
        ("City Cement Co", "Cement supplier", "0321-2220002", "Cement", "active"),
        ("Premier Sand", "Aggregates", "0321-3330003", "Aggregates", "active"),
        ("Pak Electrics", "Electrical", "0321-4440004", "Electrical", "active"),
        ("Master Tiles", "Tiles & flooring", "0321-5550005", "Tiles", "active"),
    ]
    conn.executemany(
        "INSERT INTO vendors(name, description, contact, category, status) VALUES(?,?,?,?,?)",
        vendors,
    )

    categories = [
        ("Structural Steel", 1), ("Cement", 2), ("Sand/Aggregates", 3),
        ("Electrical", 4), ("Tiles & Finishing", 5), ("Labor", 6), ("Misc", 7),
    ]
    conn.executemany(
        "INSERT INTO budget_categories(name, sort_order) VALUES(?, ?)", categories
    )

    budget_lines = [
        (1, 1, 45000000, 1), (1, 2, 12000000, 1), (1, 6, 28000000, 1),
        (2, 1, 38000000, 1), (2, 2, 10000000, 1),
    ]
    conn.executemany(
        """INSERT INTO project_budget_lines(project_id, category_id, planned_amount, revision_no)
           VALUES(?,?,?,?)""",
        budget_lines,
    )

    pos = [
        ("PO-2025-0142", 1, 1, 1, "Structural Steel", "TMT Steel Bars", "50 Tons",
         370000, 18500000, "2025-04-20", None, "ordered", "pending", "Block A"),
        ("PO-2025-0141", 2, 1, 2, "Cement", "OPC Cement", "500 Bags",
         750, 375000, "2025-04-15", None, "delivered", "done", "Block B"),
        ("PO-2025-0140", 3, 1, 3, "Aggregates", "Fine Sand", "20 Trucks",
         12000, 240000, "2025-04-10", None, "delivered", "done", "Block A"),
        ("PO-2025-0139", 4, 1, 4, "Electrical", "Electrical Conduit", "2000 m",
         2100, 4200000, "2025-04-28", None, "ordered", "na", "Block C"),
        ("PO-2025-0138", 5, 2, 5, "Tiles", "Marble Tiles", "800 sqm",
         5500, 4400000, "2025-05-01", None, "ordered", "pending", "Block A"),
    ]
    conn.executemany(
        """INSERT INTO purchase_orders(po_no, vendor_id, project_id, budget_category_id,
           category, material, quantity, unit_cost, total, order_date,
           expected_delivery_date, status, grn_status, site) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        pos,
    )

    conn.execute(
        """INSERT INTO vendor_payments(vendor_id, purchase_order_id, amount,
           payment_date, payment_method) VALUES(2, 2, 375000, '2025-04-16', 'Bank Transfer')"""
    )

    investors = [
        ("Ali Ventures", "35201-1111111-1", "0300-1111111", "ali@ventures.pk", "Company investor", "active"),
        ("Hassan Capital", "35202-2222222-2", "0300-2222222", "hassan@capital.pk", "Individual", "active"),
    ]
    conn.executemany(
        "INSERT INTO investors(name, cnic, mobile_number, email, description, status) VALUES(?,?,?,?,?,?)",
        investors,
    )

    agreements = [
        (1, 1, "monthly_return", 50000000, "2023-06-01", 1.5, None, "active"),
        (2, None, "profit_sharing", 80000000, "2024-01-15", None, 15.0, "active"),
    ]
    conn.executemany(
        """INSERT INTO investor_agreements(investor_id, project_id, investor_type,
           investment_amount, investment_date, monthly_return_pct, profit_share_pct, status)
           VALUES(?,?,?,?,?,?,?,?)""",
        agreements,
    )

    conn.execute(
        "INSERT INTO investor_contributions(agreement_id, amount, contribution_date) VALUES(1, 50000000, '2023-06-01')"
    )
    conn.execute(
        "INSERT INTO investor_distributions(agreement_id, amount, distribution_date, notes) VALUES(1, 750000, '2025-04-01', 'Monthly return Q1')"
    )


def init_db(force: bool = False) -> None:
    if force or needs_init():
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
        conn = _connect()
        init_schema(conn)
        run_seed(conn)
        conn.commit()
        conn.close()
        print(f"Database initialized: {DB_PATH}")


if __name__ == "__main__":
    init_db(force=True)
