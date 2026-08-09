from fastapi import APIRouter
from backend.database import fetch_all, fetch_one, get_db

router = APIRouter(prefix="/api", tags=["stubs"])


@router.get("/reports/ageing")
def report_ageing():
    with get_db() as conn:
        row = fetch_one(
            conn,
            """SELECT
                 COALESCE(SUM(CASE WHEN days BETWEEN 1 AND 30 THEN remaining_amount ELSE 0 END),0) AS d30,
                 COALESCE(SUM(CASE WHEN days BETWEEN 31 AND 60 THEN remaining_amount ELSE 0 END),0) AS d60,
                 COALESCE(SUM(CASE WHEN days > 60 THEN remaining_amount ELSE 0 END),0) AS d90
               FROM (
                 SELECT remaining_amount,
                        CAST(julianday('now') - julianday(due_date) AS INTEGER) AS days
                 FROM installments WHERE status='overdue' AND remaining_amount > 0
               )""",
        )
        return row or {"d90": 0, "d60": 0, "d30": 0}


@router.get("/reports/sales")
def report_sales():
    with get_db() as conn:
        return fetch_all(
            conn,
            """SELECT p.name AS project_name, COUNT(b.id) AS bookings,
                      COALESCE(SUM(b.final_sale_price),0) AS total_sales,
                      COALESCE(SUM(b.booking_amount),0) AS collected_dp
               FROM bookings b
               JOIN projects p ON p.id=b.project_id
               WHERE b.status='active'
               GROUP BY b.project_id""",
        )
