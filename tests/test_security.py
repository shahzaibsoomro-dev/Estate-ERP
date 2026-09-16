"""Authentication, roles, company isolation and document security."""
import pytest

from conftest import EMAILS, PASSWORD, login

COMPANY_API = ["/api/dashboard", "/api/customers", "/api/bookings", "/api/portal", "/api/document-templates",
               "/api/customer-documents", "/api/portal-access", "/api/projects"]


def test_public_endpoints_open(as_role):
    c = as_role(None)
    for path in ("/", "/login", "/api/health", "/api/public/overview", "/robots.txt", "/c/beta-builders"):
        assert c.get(path).status_code == 200, path
    pub = c.get("/api/public/overview").json()
    assert pub["projects"] and "cnic" not in str(pub).lower()
    assert c.get("/api/public/overview?company=beta-builders").json()["company"]["name"] == "Beta Builders"
    assert c.get("/api/public/overview?company=nope").status_code == 404


@pytest.mark.parametrize("path", COMPANY_API + ["/api/me/overview", "/api/console/companies", "/api/auth/me",
                                                "/api/company/employees"])
def test_anonymous_api_is_401(as_role, path):
    assert as_role(None).get(path).status_code == 401


def test_anonymous_pages_redirect_to_login(as_role):
    c = as_role(None)
    for path in ("/app", "/portal", "/console", "/docs", "/documents/1"):
        r = c.get(path, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"].startswith("/login?next="), path


def test_role_homes(as_role):
    assert login(as_role(None), EMAILS["superadmin"])["home"] == "/console"
    assert login(as_role(None), EMAILS["admin"])["home"] == "/app"
    assert login(as_role(None), EMAILS["employee_scoped"])["home"] == "/app"
    assert login(as_role(None), EMAILS["customer"])["home"] == "/portal"


def test_area_matrix(as_role):
    sa, admin, cust = as_role("superadmin"), as_role("admin"), as_role("customer")
    for path in COMPANY_API:
        assert admin.get(path).status_code == 200, path
        assert cust.get(path).status_code == 403, path
        assert sa.get(path).status_code == 403, path  # superadmin must enter support mode first
    assert sa.get("/api/console/companies").status_code == 200
    assert admin.get("/api/console/companies").status_code == 403
    assert admin.get("/openapi.json").status_code == 403
    assert sa.get("/openapi.json").status_code == 200
    assert cust.get("/api/me/overview").status_code == 200
    assert admin.get("/api/me/overview").status_code == 403
    assert cust.get("/app", follow_redirects=False).headers["location"] == "/portal"
    assert admin.get("/console", follow_redirects=False).headers["location"] == "/app"


def test_company_isolation(as_role, world):
    a, b = as_role("admin"), as_role("admin_b")
    a_names = {p["name"] for p in a.get("/api/projects").json()}
    b_names = {p["name"] for p in b.get("/api/projects").json()}
    assert b_names == {"Beta Towers"} and "Beta Towers" not in a_names
    assert [c["name"] for c in b.get("/api/customers").json()] == ["Beta Buyer"]
    # Ids are per company: the same id in company B never returns company A's record.
    a_cust = a.get(f"/api/customers/{world['cust1']}").json()
    r = b.get(f"/api/customers/{world['cust1']}")
    assert r.status_code == 404 or r.json()["cnic"] != a_cust["cnic"]
    # Customer logins list only shows own company.
    assert all(r["name"] == "Beta Buyer" for r in b.get("/api/portal-access").json())
    emails = {u["email"] for u in b.get("/api/company/employees").json()}
    assert emails == {EMAILS["admin_b"]}


def test_customer_sees_only_own_data(as_role, world):
    c1, c2, cb = as_role("customer"), as_role("customer2"), as_role("customer_b")
    o1, o2 = c1.get("/api/me/overview").json(), c2.get("/api/me/overview").json()
    assert o1["customer"]["cnic"] != o2["customer"]["cnic"]
    assert "nok_name" not in o1["customer"]
    assert c1.get(f"/api/me/overview?customer_id={world['cust2']}").json()["customer"] == o1["customer"]
    assert cb.get("/api/me/overview").json()["customer"]["name"] == "Beta Buyer"


def test_login_errors_are_generic(as_role, world):
    c = as_role(None)
    r1 = c.post("/api/auth/login", json={"identifier": "nobody@test.local", "password": "x" * 12})
    r2 = c.post("/api/auth/login", json={"identifier": EMAILS["admin"], "password": "wrong-pass-123"})
    assert r1.status_code == r2.status_code == 401
    assert r1.json()["detail"] == r2.json()["detail"]


def test_session_cookie_flags(as_role, world):
    c = as_role(None)
    r = c.post("/api/auth/login", json={"identifier": EMAILS["admin"], "password": PASSWORD})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie
    assert "erp_session" not in r.text


def test_csrf_required_for_writes(as_role):
    c = as_role("admin")
    token = c.headers.pop("X-CSRF-Token")
    r = c.post("/api/customer-documents", json={"template_id": 1, "customer_id": 1})
    assert r.status_code == 403 and "CSRF" in r.json()["detail"]
    c.headers["X-CSRF-Token"] = "wrong"
    assert c.post("/api/customer-documents", json={"template_id": 1, "customer_id": 1}).status_code == 403
    c.headers["X-CSRF-Token"] = token


def test_cross_origin_write_blocked(as_role):
    c = as_role("admin")
    assert c.post("/api/auth/logout", headers={"Origin": "https://evil.example"}).status_code == 403
    assert c.get("/api/auth/me").status_code == 200


def test_logout_revokes_session(as_role):
    c = as_role("admin")
    cookie = c.cookies.get("erp_session")
    assert c.post("/api/auth/logout").status_code == 200
    c.cookies.set("erp_session", cookie)
    assert c.get("/api/auth/me").status_code == 401


def test_lockout_and_admin_unlock(as_role, world):
    from backend.auth import service
    from backend.database import platform_db
    with platform_db() as conn:
        u, _ = service.create_user(conn, email="lock@test.local", name="Lock", role="employee",
                                   company_id=world["company_a"]["id"], password=PASSWORD,
                                   must_change_password=False)
    c = as_role(None)
    for _ in range(5):
        assert c.post("/api/auth/login", json={"identifier": "lock@test.local", "password": "bad-pass-000"}).status_code == 401
    assert c.post("/api/auth/login", json={"identifier": "lock@test.local", "password": PASSWORD}).status_code == 429
    admin = as_role("admin")
    emp = next(e for e in admin.get("/api/company/employees").json() if e["email"] == "lock@test.local")
    assert emp["locked"]
    assert admin.post(f"/api/company/employees/{u['id']}/unlock").status_code == 200
    login(as_role(None), "lock@test.local")


def test_forced_password_change_flow(as_role, world):
    c = as_role("admin")
    r = c.post("/api/portal-access", json={"customer_id": 3, "email": "firsttime@test.local"})
    assert r.status_code == 200, r.text
    temp = r.json()["temporary_password"]
    new = as_role(None)
    me = login(new, "firsttime@test.local", temp)
    assert me["must_change_password"] and me["home"] == "/portal"
    assert new.get("/api/me/overview").status_code == 403
    assert new.post("/api/auth/change-password", json={"current_password": temp, "new_password": "short"}).status_code == 400
    ok = new.post("/api/auth/change-password", json={"current_password": temp, "new_password": "Brand-New-Pass-9"})
    assert ok.status_code == 200 and not ok.json()["must_change_password"]
    assert new.get("/api/me/overview").status_code == 200


def test_customer_can_login_with_cnic(as_role, world):
    from backend.database import fetch_one, get_db
    with get_db(world["a_db"]) as conn:
        cnic = fetch_one(conn, "SELECT cnic FROM customers WHERE id=?", (world["cust1"],))["cnic"]
    assert login(as_role(None), cnic.replace("-", ""))["role"] == "customer"


def test_security_headers(as_role):
    r = as_role(None).get("/login")
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-frame-options"] == "SAMEORIGIN"
    assert r.headers["x-content-type-options"] == "nosniff"


def test_documents_scoped_to_owner(as_role, world):
    admin = as_role("admin")
    booking = admin.get(f"/api/portal?customer_id={world['cust1']}").json()["bookings"][0]["id"]
    tmpl = admin.get("/api/document-templates").json()["templates"][0]["id"]
    doc = admin.post("/api/customer-documents", json={
        "template_id": tmpl, "customer_id": world["cust1"], "booking_id": booking}).json()
    hidden = admin.post("/api/customer-documents", json={
        "template_id": tmpl, "customer_id": world["cust1"], "booking_id": booking, "visible_to_customer": False}).json()
    c1, c2, cb = as_role("customer"), as_role("customer2"), as_role("customer_b")
    assert c1.get(f"/documents/{doc['id']}").status_code == 200
    assert c2.get(f"/documents/{doc['id']}").status_code == 404
    assert cb.get(f"/documents/{doc['id']}").status_code == 404  # other company
    assert as_role("admin_b").get(f"/documents/{doc['id']}").status_code == 404
    assert c1.get(f"/documents/{hidden['id']}").status_code == 404
    ids = [d["id"] for d in c1.get("/api/me/documents").json()]
    assert doc["id"] in ids and hidden["id"] not in ids
    admin.patch(f"/api/customer-documents/{doc['id']}", json={"revoke": True})
    assert c1.get(f"/documents/{doc['id']}").status_code == 404


def test_booking_must_belong_to_customer(as_role, world):
    admin = as_role("admin")
    other = admin.get(f"/api/portal?customer_id={world['cust2']}").json()["bookings"][0]["id"]
    tmpl = admin.get("/api/document-templates").json()["templates"][0]["id"]
    r = admin.post("/api/customer-documents", json={"template_id": tmpl, "customer_id": world["cust1"], "booking_id": other})
    assert r.status_code == 400


@pytest.mark.parametrize("bad", [
    "<script>alert(1)</script>", '<img src=x onerror="alert(1)">', '<a href="javascript:alert(1)">x</a>',
    "<iframe src=//evil></iframe>", "{{ customer.password_hash }}",
])
def test_template_sanitisation(as_role, bad):
    assert as_role("admin").post("/api/document-templates", json={"name": "Bad", "body_html": bad}).status_code == 400


def test_values_are_escaped_in_documents():
    from backend.documents import render
    out = render.render("<p>{{customer.name}}</p>", {"values": {"customer.name": "<b onmouseover=x>"}, "blocks": {}})
    assert "<b" not in out and "&lt;b" in out


def test_session_probe_is_public(as_role):
    assert as_role(None).get("/api/auth/session").json() == {"authenticated": False}
    probe = as_role("customer").get("/api/auth/session").json()
    assert probe["authenticated"] and probe["home"] == "/portal"


def test_document_footer_falls_back_without_contact(as_role, world):
    admin = as_role("admin")
    booking = admin.get(f"/api/portal?customer_id={world['cust1']}").json()["bookings"][0]["id"]
    tmpl = next(t for t in admin.get("/api/document-templates").json()["templates"] if t["code"] == "statement_of_account")
    html = admin.post("/api/document-templates/preview", json={
        "template_id": tmpl["id"], "customer_id": world["cust1"], "booking_id": booking}).json()["html"]
    assert "contact ." not in html and "Payments received" in html
