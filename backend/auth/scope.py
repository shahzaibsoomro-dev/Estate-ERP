"""Project-level data scoping for employees who may only see selected projects.

Applied by the middleware in four ways:
  1. list filters: project_id / project_ids query parameters are forced to the allowed set
  2. resource checks: /api/<thing>/{id} and ids in request bodies must belong to an allowed project
  3. response filtering: rows that reference other projects (project_id, booking_id, unit_id,
     customer_id) are removed from JSON list responses
  4. company-wide pages (cashbook, reports, parties, activity) require access to all projects
"""
import re
from urllib.parse import parse_qsl, urlencode

from backend.database import connect

NO_PROJECT = "0"  # sentinel id that matches nothing — never let an empty filter mean "all"

# path regex -> SQL returning the project_id(s) the resource belongs to
_PATH_RESOLVERS = [
    (re.compile(r"^/api/projects/(\d+)(/|$)"), "SELECT ? AS project_id"),
    (re.compile(r"^/api/units/(\d+)(/|$)"), "SELECT project_id FROM units WHERE id=?"),
    (re.compile(r"^/api/possession/units/(\d+)(/|$)"), "SELECT project_id FROM units WHERE id=?"),
    (re.compile(r"^/api/holds/(\d+)(/|$)"),
     "SELECT u.project_id FROM unit_holds h JOIN units u ON u.id=h.unit_id WHERE h.id=?"),
    (re.compile(r"^/api/possession/checklists/(\d+)(/|$)"),
     "SELECT u.project_id FROM possession_checklists pc JOIN units u ON u.id=pc.unit_id WHERE pc.id=?"),
    (re.compile(r"^/api/bookings/(\d+)(/|$)"), "SELECT project_id FROM bookings WHERE id=?"),
    (re.compile(r"^/api/purchase-orders/(\d+)(/|$)"), "SELECT project_id FROM purchase_orders WHERE id=?"),
    (re.compile(r"^/api/site-logs/(\d+)(/|$)"), "SELECT project_id FROM site_logs WHERE id=?"),
    (re.compile(r"^/api/budget/lines/(\d+)(/|$)"), "SELECT project_id FROM project_budget_lines WHERE id=?"),
    (re.compile(r"^/api/inventory/(\d+)(/|$)"),
     "SELECT project_id FROM inventory_items WHERE id=? AND project_id IS NOT NULL"),
]
_CUSTOMER_PATHS = [re.compile(r"^/api/customers/(\d+)(/|$)")]
_DOCUMENT_PATHS = [re.compile(r"^/api/customer-documents/(\d+)(/|$)"), re.compile(r"^/documents/(\d+)$")]

_BODY_RESOLVERS = {
    "unit_id": "SELECT project_id FROM units WHERE id=?",
    "booking_id": "SELECT project_id FROM bookings WHERE id=?",
    "installment_id": "SELECT b.project_id FROM installments i JOIN bookings b ON b.id=i.booking_id WHERE i.id=?",
    "purchase_order_id": "SELECT project_id FROM purchase_orders WHERE id=?",
    "po_id": "SELECT project_id FROM purchase_orders WHERE id=?",
    "line_id": "SELECT project_id FROM project_budget_lines WHERE id=?",
}

# list endpoints whose rows use "id" for the scoped entity
_ID_KEY = {"/api/projects": "project_id", "/api/customers": "customer_id", "/api/portal": "customer_id",
           "/api/bookings": "booking_id", "/api/units": "unit_id"}


class ScopeDenied(Exception):
    pass


class Scope:
    def __init__(self, project_ids: list[int], db_path: str):
        self.projects = set(project_ids)
        self.db_path = db_path
        self._bookings = None
        self._units = None
        self._customers = None

    # ---------------------------------------------------------- lazy sets
    def _ids(self, sql: str) -> set[int]:
        if not self.projects:
            return set()
        ph = ",".join("?" * len(self.projects))
        conn = connect(self.db_path)
        try:
            return {r[0] for r in conn.execute(sql.format(ph=ph), tuple(self.projects))}
        finally:
            conn.close()

    @property
    def bookings(self) -> set[int]:
        if self._bookings is None:
            self._bookings = self._ids("SELECT id FROM bookings WHERE project_id IN ({ph})")
        return self._bookings

    @property
    def units(self) -> set[int]:
        if self._units is None:
            self._units = self._ids("SELECT id FROM units WHERE project_id IN ({ph})")
        return self._units

    @property
    def customers(self) -> set[int]:
        """Customers with a booking/hold in an allowed project, plus customers not yet tied to any project."""
        if self._customers is None:
            conn = connect(self.db_path)
            try:
                ph = ",".join("?" * len(self.projects)) or "NULL"
                rows = conn.execute(
                    f"""SELECT c.id FROM customers c
                        WHERE (NOT EXISTS (SELECT 1 FROM bookings b WHERE b.customer_id=c.id)
                               AND NOT EXISTS (SELECT 1 FROM unit_holds h WHERE h.customer_id=c.id))
                           OR EXISTS (SELECT 1 FROM bookings b WHERE b.customer_id=c.id AND b.project_id IN ({ph}))
                           OR EXISTS (SELECT 1 FROM unit_holds h JOIN units u ON u.id=h.unit_id
                                      WHERE h.customer_id=c.id AND u.project_id IN ({ph}))""",
                    tuple(self.projects) * 2,
                ).fetchall()
                self._customers = {r[0] for r in rows}
            finally:
                conn.close()
        return self._customers

    # ---------------------------------------------------------- checks
    def _project_of(self, sql: str, value) -> list:
        conn = connect(self.db_path)
        try:
            return [r[0] for r in conn.execute(sql, (value,)).fetchall()]
        finally:
            conn.close()

    def require_project(self, pid) -> None:
        if pid is None:
            return
        try:
            pid = int(pid)
        except (TypeError, ValueError) as e:
            raise ScopeDenied from e
        if pid not in self.projects:
            raise ScopeDenied

    def require_customer(self, cid) -> None:
        try:
            if int(cid) not in self.customers:
                raise ScopeDenied
        except (TypeError, ValueError) as e:
            raise ScopeDenied from e

    def check_path(self, path: str) -> None:
        for rx, sql in _PATH_RESOLVERS:
            m = rx.match(path)
            if m:
                rows = self._project_of(sql, int(m.group(1)))
                for pid in rows:
                    if pid is not None:
                        self.require_project(pid)
                return
        for rx in _CUSTOMER_PATHS:
            m = rx.match(path)
            if m:
                self.require_customer(m.group(1))
                return
        for rx in _DOCUMENT_PATHS:
            m = rx.match(path)
            if m:
                conn = connect(self.db_path)
                try:
                    row = conn.execute(
                        """SELECT d.customer_id, b.project_id FROM customer_documents d
                           LEFT JOIN bookings b ON b.id=d.booking_id WHERE d.id=?""",
                        (int(m.group(1)),),
                    ).fetchone()
                finally:
                    conn.close()
                if row:
                    self.require_customer(row[0])
                    if row[1] is not None:
                        self.require_project(row[1])
                return

    def check_query(self, params: dict) -> None:
        if params.get("project_id"):
            self.require_project(params["project_id"])
        if params.get("customer_id"):
            self.require_customer(params["customer_id"])

    def scoped_query_string(self, query_string: bytes) -> bytes:
        """Force project_ids to the allowed set (intersected with what the client asked for)."""
        pairs = parse_qsl(query_string.decode("latin-1"), keep_blank_values=True)
        asked = set()
        for k, v in pairs:
            if k == "project_ids":
                asked |= {int(x) for x in v.split(",") if x.strip().isdigit()}
            elif k == "project_id" and v.isdigit():
                asked.add(int(v))
        allowed = (asked & self.projects) if asked else set(self.projects)
        kept = [(k, v) for k, v in pairs if k not in ("project_ids", "project_id")]
        kept.append(("project_ids", ",".join(str(p) for p in sorted(allowed)) or NO_PROJECT))
        return urlencode(kept).encode("latin-1")

    def check_body(self, body) -> None:
        if not isinstance(body, dict):
            return
        if "project_id" in body:
            self.require_project(body["project_id"])
        for pid in body.get("project_ids") or []:
            self.require_project(pid)
        for key, sql in _BODY_RESOLVERS.items():
            if body.get(key) is not None:
                for pid in self._project_of(sql, body[key]):
                    if pid is not None:
                        self.require_project(pid)
        for key in ("customer_id", "to_customer_id"):
            if body.get(key) is not None:
                self.require_customer(body[key])

    # ---------------------------------------------------------- filtering
    def _row_ok(self, row: dict, id_key: str | None) -> bool:
        checks = {
            "project_id": self.projects,
            "booking_id": None,
            "unit_id": None,
            "customer_id": None,
        }
        for key in checks:
            val = row.get(key)
            if id_key == key and "id" in row:
                val = row["id"] if val is None else val
            if val is None:
                continue
            try:
                val = int(val)
            except (TypeError, ValueError):
                continue
            allowed = {"project_id": self.projects, "booking_id": self.bookings,
                       "unit_id": self.units, "customer_id": self.customers}[key]
            if val not in allowed:
                return False
        return True

    def filter(self, data, id_key: str | None = None, top: bool = True):
        if isinstance(data, list):
            return [self.filter(x, None, False) for x in data
                    if not isinstance(x, dict) or self._row_ok(x, id_key if top else None)]
        if isinstance(data, dict):
            return {k: self.filter(v, None, False) for k, v in data.items()}
        return data

    def filter_response(self, path: str, data):
        data = self.filter(data, _ID_KEY.get(path))
        if path == "/api/dashboard" and isinstance(data, dict):
            # Company-wide figures are hidden from project-limited staff.
            data["alerts"] = []
            if isinstance(data.get("kpi"), dict):
                data["kpi"]["payable"] = None
        return data
