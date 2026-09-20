"""Activity Log: readable summaries, filters, and actor enrichment."""
from backend.services import audit as audit_svc


def test_summarize_payment_and_booking():
    pay = audit_svc.summarize("payment", "recorded", {
        "amount": 50000, "receipt_no": "RCP-1001", "customer_name": "Ali Khan", "unit_no": "A-101",
    })
    assert "50,000" in pay
    assert "Ali Khan" in pay
    assert "RCP-1001" in pay

    booked = audit_svc.summarize("booking", "created", {
        "booking_no": "BK-2001", "unit_no": "B-12", "customer_name": "Sara", "sale_price": 8_000_000,
    })
    assert "B-12" in booked and "Sara" in booked and "BK-2001" in booked


def test_facts_skip_ids_and_format_money():
    items = audit_svc.facts({
        "amount": 1200, "customer_id": 9, "receipt_no": "RCP-1", "note": "Cash",
    })
    keys = {f["key"] for f in items}
    assert "customer_id" not in keys
    assert "amount" in keys and "receipt_no" in keys
    amount = next(f for f in items if f["key"] == "amount")
    assert "1,200" in amount["value"]


def test_audit_api_returns_enriched_rows(as_role):
    client = as_role("admin")
    # Seed a visible event
    with client:
        # Use an existing payment path if any audit rows already exist from fixtures;
        # otherwise create a project which now writes an audit row.
        r = client.post("/api/projects", json={
            "name": "Activity Probe Towers", "location": "Lahore", "status": "planning",
            "number_of_units": 1,
        })
        assert r.status_code == 200, r.text
        pid = r.json()["id"]

        listed = client.get("/api/audit?limit=50")
        assert listed.status_code == 200, listed.text
        body = listed.json()
        assert "rows" in body and "modules" in body and "entities" in body
        assert body["rows"], "expected at least one activity row"
        row = next((x for x in body["rows"] if x.get("entity_type") == "project" and x.get("entity_id") == pid), body["rows"][0])
        assert row.get("summary")
        assert row.get("module")
        assert row.get("actor_name")
        assert "facts" in row

        filtered = client.get("/api/audit?module=Projects&q=Activity Probe")
        assert filtered.status_code == 200
        assert any("Activity Probe" in (x.get("summary") or "") for x in filtered.json()["rows"])
