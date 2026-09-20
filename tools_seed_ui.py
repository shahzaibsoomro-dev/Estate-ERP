"""Seed a plan into the throwaway dev server so the UI can be eyeballed."""
import json
import urllib.request

BASE = "http://127.0.0.1:5058"
jar = urllib.request.HTTPCookieProcessor()
opener = urllib.request.build_opener(jar)
CSRF = {}


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json", **CSRF})
    with opener.open(req) as r:
        return json.loads(r.read() or "null")


login = call("POST", "/api/auth/login", {"identifier": "uidev@test.local", "password": "Str0ng-Test-Pass"})
CSRF["X-CSRF-Token"] = login["csrf_token"]

pid = call("GET", "/api/projects")[0]["id"]
print("project", pid)
for stage in call("GET", f"/api/planning/overview?project_id={pid}")["stages"]:
    call("DELETE", f"/api/planning/stages/{stage['id']}")

s1 = call("POST", "/api/planning/stages", {"project_id": pid, "name": "Substructure", "weight_bps": 4000,
                                           "planned_start": "2026-01-01", "planned_end": "2026-02-28"})
s2 = call("POST", "/api/planning/stages", {"project_id": pid, "name": "Grey structure", "weight_bps": 6000,
                                           "planned_start": "2026-03-01", "planned_end": "2026-06-30"})
t1 = call("POST", "/api/planning/tasks", {"stage_id": s1["id"], "name": "Excavation", "weight_bps": 5000,
                                          "planned_start": "2026-01-01", "planned_end": "2026-01-10",
                                          "workers_skilled": 2, "skilled_rate": 2500,
                                          "workers_unskilled": 4, "unskilled_rate": 1200})
t2 = call("POST", "/api/planning/tasks", {"stage_id": s1["id"], "name": "Footings", "weight_bps": 5000,
                                          "planned_start": "2026-01-05", "planned_end": "2026-01-25",
                                          "depends_on_task_id": t1["id"], "workers_skilled": 3, "skilled_rate": 2200})
t3 = call("POST", "/api/planning/tasks", {"stage_id": s2["id"], "name": "Columns & slabs", "weight_bps": 6000,
                                          "planned_start": "2026-03-01", "planned_end": "2026-04-30",
                                          "workers_skilled": 6, "skilled_rate": 2600,
                                          "workers_unskilled": 8, "unskilled_rate": 1300})
call("POST", "/api/planning/tasks", {"stage_id": s2["id"], "name": "Blockwork", "weight_bps": 4000,
                                     "planned_start": "2026-05-01", "planned_end": "2026-06-15",
                                     "depends_on_task_id": t3["id"], "workers_unskilled": 10, "unskilled_rate": 1300})
call("POST", f"/api/planning/tasks/{t1['id']}/progress", {"progress_pct": 100})
call("POST", f"/api/planning/tasks/{t2['id']}/progress", {"progress_pct": 35})

call("POST", "/api/boq/lines", {"project_id": pid, "stage_id": s1["id"], "name": "Cement", "unit": "bag",
                                "qty": 400, "wastage_pct": 10, "rate": 1200})
call("POST", "/api/boq/lines", {"project_id": pid, "stage_id": s2["id"], "name": "Steel bar 12mm", "unit": "ton",
                                "qty": 18, "wastage_pct": 5, "rate": 265000})
cat = call("GET", "/api/budget/categories")[0]
call("POST", "/api/budget/lines", {"project_id": pid, "category_id": cat["id"], "planned_amount": 4500000,
                                   "notes": "Approvals and NOCs"})

plan = call("GET", f"/api/planning/overview?project_id={pid}")
print("progress", plan["current_progress"], "computed", plan["computed_progress"],
      "labour", plan["labour_total"], "warnings", plan["warning_count"])
print("boq", call("GET", f"/api/boq/summary?project_id={pid}")["estimated_amount"])
print("rollup", call("GET", f"/api/budget/rollup?project_id={pid}"))
