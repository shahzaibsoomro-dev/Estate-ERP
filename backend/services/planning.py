"""Structure of Work — stages, tasks, schedule and the weighted progress roll-up.

Weights are basis points: stages sum to 10000 across a project, tasks sum to 10000
inside their stage. Task progress rolls up through those weights into
projects.current_progress, which is what drives the milestone installments.
"""

from datetime import date, timedelta

from backend.database import fetch_all, fetch_one
from backend.services import audit as audit_svc

BPS = 10000
STATUSES = ("not_started", "in_progress", "done", "on_hold")
STATUS_LABELS = {
    "not_started": "Not started",
    "in_progress": "In progress",
    "done": "Done",
    "on_hold": "On hold",
}


def _clean(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int(value, default=0) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _pct(value) -> int:
    return max(0, min(100, _int(value, 0)))


def _day(value) -> date | None:
    text = _clean(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _iso(value) -> str | None:
    d = _day(value)
    return d.isoformat() if d else None


def normalize_status(raw, progress: int | None = None) -> str:
    status = (_clean(raw) or "").lower().replace(" ", "_")
    if status == "on_hold":
        return "on_hold"
    if status in STATUSES and progress is None:
        return status
    p = _pct(progress)
    if p >= 100:
        return "done"
    return "in_progress" if p > 0 else "not_started"


def span_days(start, end) -> int:
    """Inclusive working span of a bar, at least one day."""
    s, e = _day(start), _day(end)
    if not s or not e or e < s:
        return 1 if (s or e) else 0
    return (e - s).days + 1


def task_labour_cost(task: dict) -> int:
    days = span_days(task.get("planned_start"), task.get("planned_end"))
    daily = (_int(task.get("workers_skilled")) * _int(task.get("skilled_rate"))
             + _int(task.get("workers_unskilled")) * _int(task.get("unskilled_rate")))
    return max(days, 0) * daily


# --------------------------------------------------------------- weights
def spread_weights(count: int) -> list[int]:
    """Even split of 10000 bps that still adds up exactly."""
    if count <= 0:
        return []
    base = BPS // count
    out = [base] * count
    out[-1] += BPS - base * count
    return out


def _weighted_progress(rows: list[dict], progress_key: str) -> int:
    """Weighted average, falling back to an even split when no weights are set."""
    if not rows:
        return 0
    total = sum(max(_int(r.get("weight_bps")), 0) for r in rows)
    if total <= 0:
        return round(sum(_pct(r.get(progress_key)) for r in rows) / len(rows))
    acc = sum(_pct(r.get(progress_key)) * max(_int(r.get("weight_bps")), 0) for r in rows)
    return round(acc / total)


def _require_project(conn, project_id) -> int:
    pid = _int(project_id, 0)
    if not pid or not fetch_one(conn, "SELECT id FROM projects WHERE id=?", (pid,)):
        raise ValueError("Project not found")
    return pid


# --------------------------------------------------------------- reads
def _stage_rows(conn, project_id: int) -> list[dict]:
    return fetch_all(
        conn,
        "SELECT * FROM project_stages WHERE project_id=? ORDER BY sort_order, id",
        (project_id,),
    )


def _task_rows(conn, project_id: int) -> list[dict]:
    return fetch_all(
        conn,
        "SELECT * FROM project_tasks WHERE project_id=? ORDER BY stage_id, sort_order, id",
        (project_id,),
    )


def _dependency_note(task: dict, by_id: dict) -> str | None:
    """Finish-to-start check. We warn, we never move the bar on our own."""
    dep = by_id.get(task.get("depends_on_task_id"))
    if not dep:
        return None
    dep_end, start = _day(dep.get("planned_end")), _day(task.get("planned_start"))
    if not dep_end or not start:
        return None
    earliest = dep_end + timedelta(days=_int(task.get("lag_days")) + 1)
    if start < earliest:
        short = (earliest - start).days
        return f"Starts {short} day(s) before “{dep['name']}” finishes"
    return None


def _decorate_task(task: dict, by_id: dict) -> dict:
    task["progress_pct"] = _pct(task.get("progress_pct"))
    task["status_label"] = STATUS_LABELS.get(task.get("status") or "not_started", "—")
    task["duration_days"] = span_days(task.get("planned_start"), task.get("planned_end"))
    task["labour_cost"] = task_labour_cost(task)
    task["weight_pct"] = round(_int(task.get("weight_bps")) / 100, 2)
    dep = by_id.get(task.get("depends_on_task_id"))
    task["depends_on_name"] = dep["name"] if dep else None
    task["dependency_warning"] = _dependency_note(task, by_id)
    return task


def overview(conn, project_id: int) -> dict:
    """Everything the Structure of Work screen and the Gantt need in one call."""
    pid = _require_project(conn, project_id)
    project = fetch_one(conn, "SELECT * FROM projects WHERE id=?", (pid,))
    stages = _stage_rows(conn, pid)
    tasks = _task_rows(conn, pid)
    by_id = {t["id"]: t for t in tasks}
    for t in tasks:
        _decorate_task(t, by_id)

    cumulative = 0
    for stage in stages:
        own = [t for t in tasks if t["stage_id"] == stage["id"]]
        stage["tasks"] = own
        stage["task_count"] = len(own)
        stage["progress_pct"] = _weighted_progress(own, "progress_pct")
        stage["labour_cost"] = sum(t["labour_cost"] for t in own)
        stage["weight_pct"] = round(_int(stage.get("weight_bps")) / 100, 2)
        starts = [d for d in (_day(t.get("planned_start")) for t in own) if d]
        ends = [d for d in (_day(t.get("planned_end")) for t in own) if d]
        stage["planned_start"] = _iso(stage.get("planned_start")) or (min(starts).isoformat() if starts else None)
        stage["planned_end"] = _iso(stage.get("planned_end")) or (max(ends).isoformat() if ends else None)
        stage["status"] = normalize_status(stage.get("status"), stage["progress_pct"])
        stage["status_label"] = STATUS_LABELS.get(stage["status"], "—")
        stage["warning_count"] = sum(1 for t in own if t["dependency_warning"])
        cumulative += _int(stage.get("weight_bps"))
        stage["cumulative_pct"] = round(cumulative / 100, 2)

    computed = _weighted_progress(stages, "progress_pct") if stages else 0
    stage_total = sum(_int(s.get("weight_bps")) for s in stages)
    task_issues = [
        {"stage_id": s["id"], "stage_name": s["name"], "total_bps": sum(_int(t.get("weight_bps")) for t in s["tasks"])}
        for s in stages
        if s["tasks"] and sum(_int(t.get("weight_bps")) for t in s["tasks"]) != BPS
    ]
    return {
        "project_id": pid,
        "project_name": project.get("name"),
        "project_status": project.get("status"),
        "progress_mode": (project.get("progress_mode") or "auto"),
        "current_progress": _pct(project.get("current_progress")),
        "computed_progress": computed,
        "stage_weight_bps": stage_total,
        "stage_weight_ok": (not stages) or stage_total == BPS,
        "task_weight_issues": task_issues,
        "labour_total": sum(s["labour_cost"] for s in stages),
        "warning_count": sum(s["warning_count"] for s in stages),
        "stages": stages,
    }


def stage_progress_hints(conn, project_id: int) -> list[dict]:
    """Read-only list used by the Pay Plans threshold editor."""
    data = overview(conn, project_id)
    return [
        {
            "id": s["id"], "name": s["name"], "weight_pct": s["weight_pct"],
            "cumulative_pct": s["cumulative_pct"], "progress_pct": s["progress_pct"],
        }
        for s in data["stages"]
    ]


def labour_total(conn, project_id: int) -> int:
    """Planned labour cost of every task in the project — feeds the budget roll-up."""
    return sum(task_labour_cost(t) for t in _task_rows(conn, _int(project_id)))


# --------------------------------------------------------------- stages
def create_stage(conn, data: dict) -> dict:
    pid = _require_project(conn, data.get("project_id"))
    name = _clean(data.get("name"))
    if not name:
        raise ValueError("Stage name is required")
    nxt = fetch_one(
        conn, "SELECT COALESCE(MAX(sort_order),0)+1 AS v FROM project_stages WHERE project_id=?", (pid,)
    )
    cur = conn.execute(
        """INSERT INTO project_stages(project_id, sort_order, name, weight_bps, planned_start,
           planned_end, status, notes) VALUES(?,?,?,?,?,?,?,?)""",
        (
            pid, _int(data.get("sort_order")) or nxt["v"], name,
            max(_int(data.get("weight_bps")), 0),
            _iso(data.get("planned_start")), _iso(data.get("planned_end")),
            normalize_status(data.get("status")) or "not_started", _clean(data.get("notes")),
        ),
    )
    audit_svc.log(conn, "project_stage", cur.lastrowid, "created", {"project_id": pid, "name": name})
    recompute_progress(conn, pid)
    return fetch_one(conn, "SELECT * FROM project_stages WHERE id=?", (cur.lastrowid,))


def update_stage(conn, stage_id: int, data: dict) -> dict:
    stage = fetch_one(conn, "SELECT * FROM project_stages WHERE id=?", (stage_id,))
    if not stage:
        raise ValueError("Stage not found")
    name = _clean(data.get("name")) if "name" in data else stage["name"]
    if not name:
        raise ValueError("Stage name is required")
    conn.execute(
        """UPDATE project_stages SET name=?, weight_bps=?, planned_start=?, planned_end=?,
           actual_start=?, actual_end=?, status=?, notes=?, sort_order=? WHERE id=?""",
        (
            name,
            max(_int(data.get("weight_bps", stage["weight_bps"])), 0),
            _iso(data.get("planned_start", stage["planned_start"])),
            _iso(data.get("planned_end", stage["planned_end"])),
            _iso(data.get("actual_start", stage["actual_start"])),
            _iso(data.get("actual_end", stage["actual_end"])),
            normalize_status(data.get("status", stage["status"])) or "not_started",
            _clean(data.get("notes", stage["notes"])),
            _int(data.get("sort_order", stage["sort_order"]), 1),
            stage_id,
        ),
    )
    recompute_progress(conn, stage["project_id"])
    return fetch_one(conn, "SELECT * FROM project_stages WHERE id=?", (stage_id,))


def delete_stage(conn, stage_id: int) -> None:
    stage = fetch_one(conn, "SELECT * FROM project_stages WHERE id=?", (stage_id,))
    if not stage:
        raise ValueError("Stage not found")
    task_ids = [r["id"] for r in fetch_all(conn, "SELECT id FROM project_tasks WHERE stage_id=?", (stage_id,))]
    for tid in task_ids:
        conn.execute("UPDATE project_tasks SET depends_on_task_id=NULL WHERE depends_on_task_id=?", (tid,))
        conn.execute("UPDATE project_boq_lines SET task_id=NULL WHERE task_id=?", (tid,))
    conn.execute("UPDATE project_boq_lines SET stage_id=NULL WHERE stage_id=?", (stage_id,))
    conn.execute("UPDATE project_budget_lines SET stage_id=NULL WHERE stage_id=?", (stage_id,))
    conn.execute("DELETE FROM project_tasks WHERE stage_id=?", (stage_id,))
    conn.execute("DELETE FROM project_stages WHERE id=?", (stage_id,))
    audit_svc.log(conn, "project_stage", stage_id, "deleted", {"name": stage["name"]})
    recompute_progress(conn, stage["project_id"])


def reorder_stages(conn, project_id: int, ordered_ids: list[int]) -> list[dict]:
    pid = _require_project(conn, project_id)
    for index, sid in enumerate(ordered_ids, start=1):
        conn.execute(
            "UPDATE project_stages SET sort_order=? WHERE id=? AND project_id=?", (index, _int(sid), pid)
        )
    return _stage_rows(conn, pid)


def even_stage_weights(conn, project_id: int) -> list[dict]:
    pid = _require_project(conn, project_id)
    stages = _stage_rows(conn, pid)
    for stage, w in zip(stages, spread_weights(len(stages))):
        conn.execute("UPDATE project_stages SET weight_bps=? WHERE id=?", (w, stage["id"]))
    recompute_progress(conn, pid)
    return _stage_rows(conn, pid)


def even_task_weights(conn, stage_id: int) -> list[dict]:
    stage = fetch_one(conn, "SELECT * FROM project_stages WHERE id=?", (stage_id,))
    if not stage:
        raise ValueError("Stage not found")
    tasks = fetch_all(
        conn, "SELECT id FROM project_tasks WHERE stage_id=? ORDER BY sort_order, id", (stage_id,)
    )
    for task, w in zip(tasks, spread_weights(len(tasks))):
        conn.execute("UPDATE project_tasks SET weight_bps=? WHERE id=?", (w, task["id"]))
    recompute_progress(conn, stage["project_id"])
    return fetch_all(conn, "SELECT * FROM project_tasks WHERE stage_id=? ORDER BY sort_order, id", (stage_id,))


# --------------------------------------------------------------- tasks
def _check_dependency(conn, task_id: int | None, dep_id, project_id: int) -> int | None:
    dep = _int(dep_id, 0)
    if not dep:
        return None
    row = fetch_one(conn, "SELECT id, project_id, depends_on_task_id FROM project_tasks WHERE id=?", (dep,))
    if not row:
        raise ValueError("Predecessor task not found")
    if row["project_id"] != project_id:
        raise ValueError("Predecessor must belong to the same project")
    if task_id and dep == task_id:
        raise ValueError("A task cannot depend on itself")
    seen = {task_id} if task_id else set()
    walk = row
    while walk and walk.get("depends_on_task_id"):
        nxt = walk["depends_on_task_id"]
        if nxt in seen or nxt == task_id:
            raise ValueError("That dependency would create a loop")
        seen.add(nxt)
        walk = fetch_one(conn, "SELECT id, depends_on_task_id FROM project_tasks WHERE id=?", (nxt,))
    return dep


def create_task(conn, data: dict) -> dict:
    stage = fetch_one(conn, "SELECT * FROM project_stages WHERE id=?", (_int(data.get("stage_id")),))
    if not stage:
        raise ValueError("Stage not found")
    name = _clean(data.get("name"))
    if not name:
        raise ValueError("Task name is required")
    pid = stage["project_id"]
    dep = _check_dependency(conn, None, data.get("depends_on_task_id"), pid)
    nxt = fetch_one(
        conn, "SELECT COALESCE(MAX(sort_order),0)+1 AS v FROM project_tasks WHERE stage_id=?", (stage["id"],)
    )
    progress = _pct(data.get("progress_pct"))
    cur = conn.execute(
        """INSERT INTO project_tasks(project_id, stage_id, sort_order, name, planned_start, planned_end,
           weight_bps, progress_pct, depends_on_task_id, lag_days, workers_skilled, workers_unskilled,
           skilled_rate, unskilled_rate, status, notes)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            pid, stage["id"], _int(data.get("sort_order")) or nxt["v"], name,
            _iso(data.get("planned_start")), _iso(data.get("planned_end")),
            max(_int(data.get("weight_bps")), 0), progress, dep, max(_int(data.get("lag_days")), 0),
            max(_int(data.get("workers_skilled")), 0), max(_int(data.get("workers_unskilled")), 0),
            max(_int(data.get("skilled_rate")), 0), max(_int(data.get("unskilled_rate")), 0),
            normalize_status(data.get("status"), progress), _clean(data.get("notes")),
        ),
    )
    audit_svc.log(conn, "project_task", cur.lastrowid, "created", {"project_id": pid, "name": name})
    recompute_progress(conn, pid)
    return fetch_one(conn, "SELECT * FROM project_tasks WHERE id=?", (cur.lastrowid,))


def update_task(conn, task_id: int, data: dict) -> dict:
    task = fetch_one(conn, "SELECT * FROM project_tasks WHERE id=?", (task_id,))
    if not task:
        raise ValueError("Task not found")
    name = _clean(data.get("name")) if "name" in data else task["name"]
    if not name:
        raise ValueError("Task name is required")
    stage_id = _int(data.get("stage_id", task["stage_id"]), task["stage_id"])
    if stage_id != task["stage_id"]:
        stage = fetch_one(conn, "SELECT * FROM project_stages WHERE id=?", (stage_id,))
        if not stage or stage["project_id"] != task["project_id"]:
            raise ValueError("Stage not found in this project")
    dep = (_check_dependency(conn, task_id, data.get("depends_on_task_id"), task["project_id"])
           if "depends_on_task_id" in data else task["depends_on_task_id"])
    progress = _pct(data.get("progress_pct", task["progress_pct"]))
    status = data.get("status", task["status"])
    conn.execute(
        """UPDATE project_tasks SET stage_id=?, sort_order=?, name=?, planned_start=?, planned_end=?,
           weight_bps=?, progress_pct=?, depends_on_task_id=?, lag_days=?, workers_skilled=?,
           workers_unskilled=?, skilled_rate=?, unskilled_rate=?, status=?, notes=? WHERE id=?""",
        (
            stage_id, _int(data.get("sort_order", task["sort_order"]), 1), name,
            _iso(data.get("planned_start", task["planned_start"])),
            _iso(data.get("planned_end", task["planned_end"])),
            max(_int(data.get("weight_bps", task["weight_bps"])), 0), progress, dep,
            max(_int(data.get("lag_days", task["lag_days"])), 0),
            max(_int(data.get("workers_skilled", task["workers_skilled"])), 0),
            max(_int(data.get("workers_unskilled", task["workers_unskilled"])), 0),
            max(_int(data.get("skilled_rate", task["skilled_rate"])), 0),
            max(_int(data.get("unskilled_rate", task["unskilled_rate"])), 0),
            normalize_status(status, None if status == "on_hold" else progress),
            _clean(data.get("notes", task["notes"])),
            task_id,
        ),
    )
    recompute_progress(conn, task["project_id"])
    if progress != task.get("progress_pct"):
        audit_svc.log(conn, "project_task", task_id, "progress", {
            "name": name, "progress_pct": progress, "project_id": task["project_id"],
        })
    return fetch_one(conn, "SELECT * FROM project_tasks WHERE id=?", (task_id,))


def delete_task(conn, task_id: int) -> None:
    task = fetch_one(conn, "SELECT * FROM project_tasks WHERE id=?", (task_id,))
    if not task:
        raise ValueError("Task not found")
    conn.execute("UPDATE project_tasks SET depends_on_task_id=NULL WHERE depends_on_task_id=?", (task_id,))
    conn.execute("UPDATE project_boq_lines SET task_id=NULL WHERE task_id=?", (task_id,))
    conn.execute("DELETE FROM project_tasks WHERE id=?", (task_id,))
    audit_svc.log(conn, "project_task", task_id, "deleted", {"name": task["name"]})
    recompute_progress(conn, task["project_id"])


def move_task(conn, task_id: int, planned_start, planned_end=None, keep_duration: bool = False) -> dict:
    """Gantt drag/resize: set the bar's dates, optionally sliding it by its own length."""
    task = fetch_one(conn, "SELECT * FROM project_tasks WHERE id=?", (task_id,))
    if not task:
        raise ValueError("Task not found")
    start = _day(planned_start) or _day(task["planned_start"])
    if not start:
        raise ValueError("A start date is required")
    if keep_duration:
        end = start + timedelta(days=max(span_days(task["planned_start"], task["planned_end"]), 1) - 1)
    else:
        end = _day(planned_end) or _day(task["planned_end"]) or start
    if end < start:
        raise ValueError("Finish date cannot be before the start date")
    conn.execute(
        "UPDATE project_tasks SET planned_start=?, planned_end=? WHERE id=?",
        (start.isoformat(), end.isoformat(), task_id),
    )
    audit_svc.log(conn, "project_task", task_id, "rescheduled", {
        "name": task["name"], "planned_start": start.isoformat(), "planned_end": end.isoformat(),
        "project_id": task["project_id"],
    })
    return fetch_one(conn, "SELECT * FROM project_tasks WHERE id=?", (task_id,))


def set_task_progress(conn, task_id: int, progress) -> dict:
    return update_task(conn, task_id, {"progress_pct": progress, "status": None})


# --------------------------------------------------------------- roll-up
def recompute_progress(conn, project_id: int) -> dict:
    """Roll tasks up through stage weights and hand the number to projects.set_progress."""
    from backend.services import projects as projects_svc

    pid = _int(project_id)
    stages = _stage_rows(conn, pid)
    tasks = _task_rows(conn, pid)
    rolled = []
    for stage in stages:
        own = [t for t in tasks if t["stage_id"] == stage["id"]]
        pct = _weighted_progress(own, "progress_pct")
        rolled.append({"weight_bps": stage["weight_bps"], "progress_pct": pct})
        starts = [d for d in (_day(t.get("planned_start")) for t in own) if d]
        actual_start = stage["actual_start"]
        actual_end = stage["actual_end"]
        if pct > 0 and not actual_start:
            actual_start = (min(starts).isoformat() if starts else date.today().isoformat())
        if pct >= 100 and not actual_end:
            actual_end = date.today().isoformat()
        if pct < 100:
            actual_end = None
        status = normalize_status(stage["status"], pct)
        conn.execute(
            "UPDATE project_stages SET status=?, actual_start=?, actual_end=? WHERE id=?",
            (status, actual_start, actual_end, stage["id"]),
        )
    computed = _weighted_progress(rolled, "progress_pct") if rolled else 0
    project = fetch_one(conn, "SELECT progress_mode, current_progress FROM projects WHERE id=?", (pid,))
    applied = (projects_svc.set_progress(conn, pid, computed, source="planning")
               if project else 0)
    return {
        "project_id": pid,
        "computed_progress": computed,
        "current_progress": applied,
        "progress_mode": (project or {}).get("progress_mode") or "auto",
    }


def set_progress_mode(conn, project_id: int, mode: str) -> dict:
    from backend.services import projects as projects_svc

    pid = _require_project(conn, project_id)
    normalized = projects_svc.normalize_progress_mode(mode)
    conn.execute("UPDATE projects SET progress_mode=? WHERE id=?", (normalized, pid))
    if normalized == "auto":
        return recompute_progress(conn, pid)
    project = fetch_one(conn, "SELECT current_progress FROM projects WHERE id=?", (pid,))
    return {
        "project_id": pid,
        "computed_progress": overview(conn, pid)["computed_progress"],
        "current_progress": _pct(project.get("current_progress")),
        "progress_mode": normalized,
    }
