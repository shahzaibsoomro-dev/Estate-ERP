from fastapi import APIRouter
from backend.database import fetch_all, get_db

router = APIRouter(prefix="/api", tags=["stubs"])


@router.get("/ledger")
def ledger():
    with get_db() as conn:
        return {"entries": [], "revenue": 0, "expenses": 0, "profit": 0}


@router.post("/ledger")
def add_ledger(body: dict):
    return {"ok": True}


@router.get("/reports/ageing")
def report_ageing():
    with get_db() as conn:
        from backend.database import fetch_one
        row = fetch_one(
            conn,
            """SELECT
                 COALESCE(SUM(CASE WHEN julianday('now')-julianday(due_date)>=90
                   THEN remaining_amount ELSE 0 END),0) AS d90,
                 COALESCE(SUM(CASE WHEN julianday('now')-julianday(due_date)>=60
                   AND julianday('now')-julianday(due_date)<90 THEN remaining_amount ELSE 0 END),0) AS d60,
                 COALESCE(SUM(CASE WHEN julianday('now')-julianday(due_date)>=30
                   AND julianday('now')-julianday(due_date)<60 THEN remaining_amount ELSE 0 END),0) AS d30
               FROM installments WHERE status='overdue'""",
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
