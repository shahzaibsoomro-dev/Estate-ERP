from fastapi import APIRouter, Query
from backend.database import get_db, fetch_one
from backend.services import dashboard as dash_svc
from backend.services.project_filter import parse_project_ids

router = APIRouter(prefix="/api", tags=["recovery"])


def _recovery(conn, project_ids: list[int] | None):
    overdue = dash_svc.get_overdue_list(conn, project_ids)
    if project_ids:
        ph = ",".join("?" * len(project_ids))
        totals = fetch_one(
            conn,
            f"""SELECT COALESCE(SUM(i.remaining_amount),0) AS receivable,
                      COALESCE(SUM(CASE WHEN i.status='overdue' THEN i.remaining_amount ELSE 0 END),0) AS overdue_amt
               FROM installments i
               JOIN units u ON u.id=i.unit_id
               WHERE i.status IN ('pending','partial','overdue')
                 AND u.project_id IN ({ph})""",
            tuple(project_ids),
        )
        collected = fetch_one(
            conn,
            f"""SELECT COALESCE(SUM(p.amount),0) AS v FROM payments p
               JOIN bookings b ON b.id=p.booking_id
               WHERE p.payment_date >= date('now','-30 days')
                 AND b.project_id IN ({ph})""",
            tuple(project_ids),
        )
    else:
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


@router.get("/recovery")
def recovery(
    project_id: int | None = Query(None),
    project_ids: str | None = Query(None),
):
    ids = parse_project_ids(project_ids, project_id)
    with get_db() as conn:
        return _recovery(conn, ids)


@router.get("/demand-notices")
def demand_notices(
    project_id: int | None = Query(None),
    project_ids: str | None = Query(None),
):
    ids = parse_project_ids(project_ids, project_id)
    with get_db() as conn:
        return dash_svc.get_overdue_list(conn, ids)
