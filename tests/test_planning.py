"""Planning module: Structure of Work weights, dependencies, progress roll-up, BOQ and budget."""
import pytest


@pytest.fixture
def admin(as_role):
    return as_role("admin")


@pytest.fixture
def plan_project(admin):
    """A throwaway project with a two-stage structure of work."""
    p = admin.post("/api/projects", json={
        "name": "Planning Sandbox", "location": "Lahore", "status": "under_construction",
        "number_of_floors": 2, "number_of_units": 4,
    })
    assert p.status_code == 200, p.text
    pid = p.json()["id"]
    s1 = admin.post("/api/planning/stages", json={
        "project_id": pid, "name": "Substructure", "weight_bps": 4000,
        "planned_start": "2026-01-01", "planned_end": "2026-02-28"}).json()
    s2 = admin.post("/api/planning/stages", json={
        "project_id": pid, "name": "Superstructure", "weight_bps": 6000,
        "planned_start": "2026-03-01", "planned_end": "2026-06-30"}).json()
    return {"id": pid, "stage1": s1["id"], "stage2": s2["id"]}


def _task(admin, stage_id, name, **kw):
    body = {"stage_id": stage_id, "name": name, "weight_bps": 5000,
            "planned_start": "2026-01-01", "planned_end": "2026-01-10", **kw}
    r = admin.post("/api/planning/tasks", json=body)
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------------ weights
def test_even_split_helpers_add_up_to_full_weight(admin, plan_project):
    admin.post("/api/planning/stages", json={"project_id": plan_project["id"], "name": "Finishes"})
    stages = admin.post(f"/api/planning/even-stage-weights?project_id={plan_project['id']}").json()
    assert sum(s["weight_bps"] for s in stages) == 10000
    assert len(stages) == 3

    for n in range(3):
        _task(admin, plan_project["stage1"], f"Task {n}", weight_bps=0)
    tasks = admin.post(f"/api/planning/stages/{plan_project['stage1']}/even-task-weights").json()
    assert sum(t["weight_bps"] for t in tasks) == 10000


def test_overview_flags_weights_that_do_not_add_up(admin, plan_project):
    _task(admin, plan_project["stage1"], "Excavation", weight_bps=3000)
    data = admin.get(f"/api/planning/overview?project_id={plan_project['id']}").json()
    assert data["stage_weight_ok"] is True          # 4000 + 6000
    assert data["task_weight_issues"][0]["total_bps"] == 3000


# ------------------------------------------------------------------ dependencies
def test_dependency_cycles_are_rejected(admin, plan_project):
    a = _task(admin, plan_project["stage1"], "Excavation")
    b = _task(admin, plan_project["stage1"], "Footings", depends_on_task_id=a["id"])
    r = admin.put(f"/api/planning/tasks/{a['id']}", json={"depends_on_task_id": b["id"]})
    assert r.status_code == 400 and "loop" in r.json()["detail"]
    assert admin.put(f"/api/planning/tasks/{a['id']}",
                     json={"depends_on_task_id": a["id"]}).status_code == 400


def test_dependency_violation_warns_but_keeps_the_dates(admin, plan_project):
    a = _task(admin, plan_project["stage1"], "Excavation",
              planned_start="2026-01-01", planned_end="2026-01-10")
    b = _task(admin, plan_project["stage1"], "Footings", depends_on_task_id=a["id"],
              planned_start="2026-01-05", planned_end="2026-01-20")
    data = admin.get(f"/api/planning/overview?project_id={plan_project['id']}").json()
    tasks = {t["id"]: t for s in data["stages"] for t in s["tasks"]}
    assert tasks[b["id"]]["dependency_warning"]
    assert tasks[b["id"]]["planned_start"] == "2026-01-05"   # nothing was auto-moved
    assert data["warning_count"] == 1

    moved = admin.post(f"/api/planning/tasks/{b['id']}/move",
                       json={"planned_start": "2026-01-11", "keep_duration": True}).json()
    assert moved["planned_start"] == "2026-01-11" and moved["planned_end"] == "2026-01-26"
    after = admin.get(f"/api/planning/overview?project_id={plan_project['id']}").json()
    assert after["warning_count"] == 0


def test_a_task_cannot_depend_on_another_project(admin, plan_project, world):
    other = admin.post("/api/planning/stages", json={
        "project_id": world["other_project"], "name": "Foreign stage"}).json()
    foreign = admin.post("/api/planning/tasks", json={"stage_id": other["id"], "name": "Foreign task"}).json()
    r = admin.post("/api/planning/tasks", json={
        "stage_id": plan_project["stage1"], "name": "Linked", "depends_on_task_id": foreign["id"]})
    assert r.status_code == 400 and "same project" in r.json()["detail"]


# ------------------------------------------------------------------ progress roll-up
def test_progress_rolls_up_through_stage_and_task_weights(admin, plan_project):
    a = _task(admin, plan_project["stage1"], "Excavation", weight_bps=5000)
    _task(admin, plan_project["stage1"], "Footings", weight_bps=5000)
    _task(admin, plan_project["stage2"], "Columns", weight_bps=10000)

    admin.post(f"/api/planning/tasks/{a['id']}/progress", json={"progress_pct": 100})
    data = admin.get(f"/api/planning/overview?project_id={plan_project['id']}").json()
    stage1 = next(s for s in data["stages"] if s["id"] == plan_project["stage1"])
    assert stage1["progress_pct"] == 50 and stage1["status"] == "in_progress"
    # half of stage 1 (40% of the project) is done
    assert data["computed_progress"] == 20
    assert admin.get(f"/api/projects/{plan_project['id']}").json()["current_progress"] == 20


def test_manual_override_wins_over_the_recompute(admin, plan_project):
    a = _task(admin, plan_project["stage1"], "Excavation", weight_bps=10000)
    admin.post(f"/api/planning/tasks/{a['id']}/progress", json={"progress_pct": 50})
    assert admin.get(f"/api/projects/{plan_project['id']}").json()["current_progress"] == 20

    admin.post("/api/planning/progress-mode", json={"project_id": plan_project["id"], "progress_mode": "manual"})
    admin.put(f"/api/projects/{plan_project['id']}", json={"current_progress": 65})
    admin.post(f"/api/planning/tasks/{a['id']}/progress", json={"progress_pct": 100})
    data = admin.get(f"/api/planning/overview?project_id={plan_project['id']}").json()
    assert data["computed_progress"] == 40 and data["current_progress"] == 65

    back = admin.post("/api/planning/progress-mode",
                      json={"project_id": plan_project["id"], "progress_mode": "auto"}).json()
    assert back["current_progress"] == 40


def test_completing_tasks_activates_milestone_installments(admin, plan_project, world):
    pid = plan_project["id"]
    admin.put(f"/api/projects/{pid}/installment-template", json={
        "name": "Construction linked", "default_booking_bps": 2000,
        "rules": [{"label": "Grey structure", "amount_bps": 10000, "trigger_kind": "construction",
                   "milestone_progress": 40, "due_days_after_trigger": 7}],
    })
    unit = admin.post("/api/units", json={
        "project_id": pid, "unit_no": "PS-1", "unit_type": "residential", "price": 5_000_000}).json()
    customer = admin.post("/api/customers", json={
        "name": "Plan Buyer", "cnic": "31111-3111113-1", "phone": "0300-9998887"}).json()
    booking = admin.post("/api/bookings", json={
        "project_id": pid, "customer_id": customer["id"], "unit_id": unit["id"], "sale_price": 5_000_000,
        "booking_amount": 1_000_000, "booking_date": "2026-01-05", "plan_source": "template"})
    assert booking.status_code == 200, booking.text

    task = _task(admin, plan_project["stage1"], "Excavation", weight_bps=10000)
    _task(admin, plan_project["stage2"], "Columns", weight_bps=10000)
    admin.post(f"/api/planning/tasks/{task['id']}/progress", json={"progress_pct": 100})

    from backend.database import fetch_all, get_db
    with get_db(world["a_db"]) as conn:
        rows = fetch_all(conn, "SELECT trigger_label, status FROM installments WHERE booking_id=?",
                         (booking.json()["booking_id"],))
    milestone = [i for i in rows if "Grey structure" in (i["trigger_label"] or "")]
    assert milestone and milestone[0]["status"] == "pending"


# ------------------------------------------------------------------ BOQ
def test_boq_compares_estimate_with_purchases_and_site_usage(admin, plan_project):
    pid = plan_project["id"]
    vendor = admin.post("/api/vendors", json={"name": "Planning Cement Co", "contact": "0300-1234567"}).json()
    line = admin.post("/api/boq/lines", json={
        "project_id": pid, "stage_id": plan_project["stage1"], "name": "Cement",
        "unit": "bag", "qty": 100, "wastage_pct": 10, "rate": 1200}).json()
    assert line["estimated_qty"] == 110 and line["estimated_amount"] == 132000

    admin.post("/api/purchase-orders", json={
        "vendor_id": vendor["id"], "project_id": pid, "material": "Cement", "quantity": "80 bag",
        "pack_qty": 80, "pack_size": 1, "pack_unit": "bag", "unit_cost": 1200, "total": 96000,
        "order_date": "2026-01-06"})
    admin.post("/api/site-logs", json={
        "project_id": pid, "log_date": "2026-01-08", "engineer": "Ali", "work_done": "Footing pour",
        "materials": [{"name": "Cement", "qty": 30, "unit": "bag"}]})

    summary = admin.get(f"/api/boq/summary?project_id={pid}").json()
    row = summary["lines"][0]
    assert row["purchased_qty"] == 80 and row["purchased_amount"] == 96000
    assert row["consumed_site_qty"] == 30 and row["consumed_qty"] == 30
    assert row["status"] == "Within estimate"
    assert summary["estimated_amount"] == 132000

    admin.put(f"/api/boq/lines/{line['id']}", json={"qty": 20})
    reread = admin.get(f"/api/boq/summary?project_id={pid}").json()["lines"][0]
    assert reread["status"] == "Over estimate" and reread["revision_no"] == 2


def test_boq_links_must_belong_to_the_same_project(admin, plan_project, world):
    r = admin.post("/api/boq/lines", json={
        "project_id": world["other_project"], "stage_id": plan_project["stage1"], "name": "Steel"})
    assert r.status_code == 400


# ------------------------------------------------------------------ budget roll-up
def test_budget_planned_is_manual_plus_boq_plus_labour(admin, plan_project):
    pid = plan_project["id"]
    categories = admin.get("/api/budget/categories").json()
    land = next(c for c in categories if c["name"] not in ("Labour", "Labor"))
    admin.post("/api/budget/lines", json={
        "project_id": pid, "category_id": land["id"], "planned_amount": 500_000, "notes": "Approvals"})
    admin.post("/api/boq/lines", json={
        "project_id": pid, "name": "Steel", "unit": "ton", "qty": 10, "rate": 250_000,
        "category_id": land["id"]})
    _task(admin, plan_project["stage1"], "Excavation", weight_bps=10000,
          planned_start="2026-01-01", planned_end="2026-01-10",
          workers_skilled=2, skilled_rate=2500, workers_unskilled=4, unskilled_rate=1200)

    rollup = admin.get(f"/api/budget/rollup?project_id={pid}").json()
    assert rollup["manual_amount"] == 500_000
    assert rollup["boq_amount"] == 2_500_000
    assert rollup["labour_amount"] == 10 * (2 * 2500 + 4 * 1200)   # 10 days on site
    assert rollup["planned_amount"] == rollup["manual_amount"] + rollup["boq_amount"] + rollup["labour_amount"]
    land_row = next(r for r in rollup["categories"] if r["category_id"] == land["id"])
    assert land_row["planned_amount"] == 3_000_000

    reports = admin.get("/api/reports/budget").json()
    assert any(r["project_id"] == pid and r["planned_amount"] for r in reports["lines"])


# ------------------------------------------------------------------ scoping
def test_planning_is_project_scoped_for_employees(as_role, admin, world):
    sales = as_role("employee_scoped")
    stage = admin.post("/api/planning/stages", json={
        "project_id": world["other_project"], "name": "Off limits"}).json()
    task = admin.post("/api/planning/tasks", json={"stage_id": stage["id"], "name": "Off limits task"}).json()
    line = admin.post("/api/boq/lines", json={
        "project_id": world["other_project"], "name": "Off limits sand", "qty": 1, "rate": 1}).json()

    assert sales.get(f"/api/planning/overview?project_id={world['other_project']}").status_code == 403
    assert sales.put(f"/api/planning/stages/{stage['id']}", json={"name": "Nope"}).status_code == 403
    assert sales.post(f"/api/planning/tasks/{task['id']}/progress", json={"progress_pct": 100}).status_code == 403
    assert sales.delete(f"/api/boq/lines/{line['id']}").status_code == 403
    assert sales.post("/api/planning/stages", json={
        "project_id": world["other_project"], "name": "Nope"}).status_code == 403
    # The sales preset has no planning rights at all, even on its own project.
    assert sales.post("/api/planning/stages", json={
        "project_id": world["scoped_project"], "name": "Nope"}).status_code == 403


def test_site_preset_can_run_the_plan(as_role, world):
    from backend.auth import service
    from backend.auth.permissions import preset_permissions
    from backend.database import platform_db
    emp = world["ids"]["employee_scoped"]
    with platform_db() as conn:
        service.set_employee_access(conn, emp, permissions=preset_permissions("site"),
                                    all_projects=False, project_ids=[world["scoped_project"]])
    try:
        site = as_role("employee_scoped")
        stage = site.post("/api/planning/stages", json={
            "project_id": world["scoped_project"], "name": "Site stage"})
        assert stage.status_code == 200, stage.text
        assert site.get(f"/api/planning/overview?project_id={world['scoped_project']}").status_code == 200
        assert site.delete(f"/api/planning/stages/{stage.json()['id']}").status_code == 403  # no delete right
    finally:
        with platform_db() as conn:
            service.set_employee_access(conn, emp, permissions=preset_permissions("sales"),
                                        all_projects=False, project_ids=[world["scoped_project"]])
