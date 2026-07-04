from fastapi import APIRouter
from backend.database import get_db
from backend.services import dashboard as dash_svc

router = APIRouter(prefix="/api", tags=["recovery"])


@router.get("/recovery")
def recovery():
    with get_db() as conn:
        overdue = dash_svc.get_overdue_list(conn)
        from backend.database import fetch_one
        totals = fetch_one(
            conn,
            """SELECT COALESCE(SUM(remaining_amount),0) AS receivable,
                      COALESCE(SUM(CASE WHEN status='overdue' THEN remaining_amount ELSE 0 END),0) AS overdue_amt
               FROM installments WHERE status IN ('pending','partial','overdue')""",
        )
        collected = fetch_one(
            conn,
            "SELECT COALESCE(SUM(amount),0) AS v FROM payments WHERE payment_date >= date('now','-30 days')",
        )
        return {
            "overdue": overdue,
            "receivable": totals["receivable"] if totals else 0,
            "overdue_amt": totals["overdue_amt"] if totals else 0,
            "collected_month": collected["v"] if collected else 0,
        }


@router.get("/demand-notices")
def demand_notices():
    with get_db() as conn:
        return dash_svc.get_overdue_list(conn)
