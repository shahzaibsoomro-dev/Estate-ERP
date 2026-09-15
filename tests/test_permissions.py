"""Employee permission matrix and project scoping."""
from conftest import EMAILS, login


def test_employee_me_contains_permissions(as_role, world):
    me = as_role("employee_scoped").get("/api/auth/me").json()
    assert me["role"] == "employee"
    assert me["project_ids"] == [world["scoped_project"]]
    assert me["permissions"]["booking"]["add"] and not me["permissions"]["booking"].get("delete")
    assert "accounts" not in me["permissions"]


def test_module_permissions_enforced(as_role):
    viewer = as_role("employee_all")      # read-only on every page
    sales = as_role("employee_scoped")    # sales preset
    assert viewer.get("/api/ledger").status_code == 200
    assert viewer.post("/api/ledger", json={}).json()["detail"] == "permission_denied"
    assert viewer.delete("/api/customers/1").status_code == 403
    assert sales.get("/api/ledger").status_code == 403          # no accounts access
    assert sales.get("/api/vendors").status_code == 403
    assert sales.get("/api/reports/ageing").status_code == 403
    assert sales.delete("/api/customers/999999").status_code == 403  # no delete right


def test_admin_only_areas_blocked_for_employees(as_role):
    emp = as_role("employee_all")
    assert emp.get("/api/company/employees").status_code == 403
    assert emp.get("/api/company/subscription").status_code == 403
    assert emp.put("/api/settings/cancellation_forfeit_pct", json={"value": "0"}).status_code == 403
    assert emp.get("/api/settings").status_code == 200  # read needed by many pages


def test_unknown_routes_default_deny_for_employees(as_role):
    emp = as_role("employee_all")
    assert emp.post("/api/holds/expire-due").status_code == 403  # viewer has no edit
    assert emp.get("/api/some/new/route").status_code == 403


def test_project_scope_filters_lists(as_role, world):
    sales = as_role("employee_scoped")
    projects = sales.get("/api/projects").json()
    assert [p["id"] for p in projects] == [world["scoped_project"]]
    units = sales.get("/api/units").json()
    assert units and all(u["project_id"] == world["scoped_project"] for u in units)
    # Asking for another project returns nothing rather than leaking it.
    assert sales.get(f"/api/units?project_ids={world['other_project']}").json() == []
    customers = {c["id"] for c in sales.get("/api/customers").json()}
    assert world["cust1"] in customers and world["cust2"] not in customers
    dash = sales.get("/api/dashboard").json()
    assert dash["kpi"]["payable"] is None and dash["alerts"] == []
    full = as_role("admin").get("/api/dashboard").json()
    assert dash["kpi"]["total_units"] < full["kpi"]["total_units"]


def test_project_scope_blocks_other_resources(as_role, world):
    sales = as_role("employee_scoped")
    assert sales.get(f"/api/projects/{world['other_project']}").status_code == 403
    assert sales.get(f"/api/customers/{world['cust2']}").status_code == 403
    assert sales.get(f"/api/customers/{world['cust1']}").status_code == 200
    assert sales.get(f"/api/portal?customer_id={world['cust2']}").status_code == 403
    admin = as_role("admin")
    other_unit = next(u for u in admin.get("/api/units").json() if u["project_id"] == world["other_project"])
    assert sales.get(f"/api/units/{other_unit['id']}").status_code == 403
    # Writes referencing another project are refused before reaching the business logic.
    r = sales.post("/api/bookings", json={"customer_id": world["cust1"], "unit_id": other_unit["id"],
                                          "sale_price": 1, "booking_amount": 1})
    assert r.status_code == 403
    assert sales.post("/api/projects", json={"name": "Sneaky"}).status_code == 403


def test_scoped_employee_cannot_open_company_wide_pages(as_role, world):
    from backend.auth import service
    from backend.auth.permissions import preset_permissions
    from backend.database import platform_db
    with platform_db() as conn:
        service.set_employee_access(conn, world["ids"]["employee_scoped"],
                                    permissions={**preset_permissions("sales"), "accounts": {"view": True}},
                                    all_projects=False, project_ids=[world["scoped_project"]])
        perms = service.get_permissions(conn, world["ids"]["employee_scoped"])
        assert "accounts" not in perms  # stripped: cashbook is company-wide
        service.set_employee_access(conn, world["ids"]["employee_scoped"], permissions=preset_permissions("sales"),
                                    all_projects=False, project_ids=[world["scoped_project"]])


def test_admin_manages_employees(as_role, world):
    admin = as_role("admin")
    cat = admin.get("/api/company/access-catalogue").json()
    assert any(m["key"] == "booking" for m in cat["modules"]) and cat["presets"]
    r = admin.post("/api/company/employees", json={
        "name": "Site Guy", "email": "site@test.local", "job_title": "Engineer",
        "permissions": {"site": {"view": True, "add": True}}, "all_projects": False,
        "project_ids": [world["scoped_project"]]})
    assert r.status_code == 200, r.text
    emp = r.json()["user"]
    assert emp["permissions"]["site"] == {"view": True, "add": True, "edit": False, "delete": False}
    temp = r.json()["temporary_password"]
    c = as_role(None)
    login(c, "site@test.local", temp)
    c.post("/api/auth/change-password", json={"current_password": temp, "new_password": "Quartz-Lamp-4823"})
    assert c.get("/api/site-logs").status_code == 200
    assert c.get("/api/customers").status_code == 403
    # Admin widens access; takes effect on the next request.
    upd = admin.put(f"/api/company/employees/{emp['id']}", json={
        "name": "Site Guy", "job_title": "Engineer", "permissions": {"site": {"view": True}, "customers": {"view": True}},
        "all_projects": True, "project_ids": []})
    assert upd.status_code == 200 and upd.json()["project_ids"] is None
    assert c.get("/api/customers").status_code == 200
    # Deactivate → signed out.
    assert admin.post(f"/api/company/employees/{emp['id']}/status", json={"is_active": False}).status_code == 200
    assert c.get("/api/auth/me").status_code == 401


def test_admin_cannot_touch_other_company_employees(as_role, world):
    b = as_role("admin_b")
    emp_id = world["ids"]["employee_scoped"]
    assert b.post(f"/api/company/employees/{emp_id}/reset-password").status_code == 404
    assert b.put(f"/api/company/employees/{emp_id}", json={"name": "x", "permissions": {}}).status_code == 404
    assert b.post(f"/api/portal-access/{world['ids']['customer']}/reset-password").status_code == 404


def test_employee_project_ids_validated(as_role):
    r = as_role("admin").post("/api/company/employees", json={
        "name": "Bad", "email": "bad@test.local", "permissions": {}, "all_projects": False, "project_ids": [987654]})
    assert r.status_code == 400


def test_invalid_permission_keys_ignored(as_role):
    r = as_role("admin").post("/api/company/employees", json={
        "name": "Odd", "email": "odd@test.local", "all_projects": True,
        "permissions": {"hacker": {"view": True}, "reports": {"delete": True, "view": True}}})
    assert r.status_code == 200
    assert r.json()["user"]["permissions"] == {"reports": {"view": True, "add": False, "edit": False, "delete": False}}


def test_scoped_employee_allowed_write_passes_body_through(as_role):
    sales = as_role("employee_scoped")
    r = sales.post("/api/customers", json={"name": "Walk-in Buyer", "cnic": "55555-5555555-5", "phone": "0300-1112223"})
    assert r.status_code == 200, r.text
    created = r.json()
    assert created["name"] == "Walk-in Buyer"
    # New customers without bookings are visible to the project-limited employee who created them.
    assert created["id"] in {c["id"] for c in sales.get("/api/customers").json()}
