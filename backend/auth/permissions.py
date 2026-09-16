"""Employee permission model.

Each API route belongs to one module (a page in the ERP) and needs one action:
view / add / edit / delete. Admins have every permission in their company;
employees get exactly what their admin ticks. Routes not listed here are
admin-only (deny by default for employees).
"""
import re

ACTIONS = ("view", "add", "edit", "delete")

# key, label, group, actions that make sense for the module, project_scoped
MODULES = [
    ("dashboard", "Dashboard", "Overview", ("view",), True),
    ("activity", "Activity log", "Overview", ("view",), False),
    ("projects", "Projects", "Inventory", ACTIONS, True),
    ("units", "Unit inventory, holds & possession", "Inventory", ACTIONS, True),
    ("booking", "Bookings (new, cancel, transfer)", "Sales & CRM", ("view", "add", "edit", "delete"), True),
    ("customers", "Customers", "Sales & CRM", ACTIONS, True),
    ("demand", "Demand notices", "Sales & CRM", ("view",), True),
    ("documents", "Documents & templates", "Sales & CRM", ("view", "add", "edit"), True),
    ("recovery", "Recovery & customer payments", "Sales & CRM", ("view", "add"), True),
    ("procurement", "Procurement (POs & vendor payments)", "Construction", ("view", "add", "edit"), True),
    ("vendors", "Vendors", "Construction", ACTIONS, False),
    ("contractors", "Contractors", "Construction", ACTIONS, True),
    ("inventory", "Materials", "Construction", ("view", "add", "edit"), True),
    ("site", "Site management", "Construction", ACTIONS, True),
    ("accounts", "Accounts / cashbook", "Finance", ("view", "add", "delete"), False),
    ("budget", "Budget", "Finance", ACTIONS, True),
    ("payplans", "Pay plans", "Finance", ("view", "edit", "delete"), True),
    ("reports", "Reports", "Finance", ("view",), False),
    ("agents", "Agents & commissions", "Stakeholders", ACTIONS, False),
    ("investors", "Investors", "Stakeholders", ACTIONS, True),
    ("partners", "Partners", "Stakeholders", ACTIONS, True),
    ("parties", "Parties (master IDs)", "Stakeholders", ("view",), False),
    ("portal", "Customer portal preview", "Administration", ("view",), True),
    ("customer_logins", "Customer portal logins", "Administration", ("view", "add", "edit"), False),
]
MODULE_KEYS = [m[0] for m in MODULES]
MODULE_ACTIONS = {m[0]: m[3] for m in MODULES}
# Modules whose data is company-wide; employees limited to some projects cannot open them.
NEEDS_ALL_PROJECTS = {"activity", "accounts", "reports", "parties"}

PRESETS = {
    "sales": {
        "label": "Sales officer",
        "perms": {"dashboard": "v", "projects": "v", "units": "va", "booking": "va", "customers": "vae",
                  "documents": "va", "demand": "v", "portal": "v", "customer_logins": "va"},
    },
    "recovery": {
        "label": "Recovery officer",
        "perms": {"dashboard": "v", "units": "v", "customers": "ve", "recovery": "va", "demand": "v",
                  "documents": "va", "portal": "v"},
    },
    "accountant": {
        "label": "Accountant",
        "perms": {"dashboard": "v", "recovery": "va", "accounts": "va", "budget": "vae", "procurement": "v",
                  "vendors": "v", "reports": "v", "agents": "ve", "investors": "ve", "partners": "ve"},
    },
    "site": {
        "label": "Site engineer",
        "perms": {"projects": "v", "units": "v", "site": "vae", "inventory": "vae", "procurement": "va",
                  "contractors": "v"},
    },
    "viewer": {
        "label": "Read-only manager",
        "perms": {k: "v" for k in MODULE_KEYS if k != "customer_logins"},
    },
}

# (methods, path regex, module(s) any-of, action). First match wins.
# A tuple of modules means "any of these grants access" (shared lookups used by several pages).
_R = [
    # --- lookups shared across pages
    ("GET", r"/api/projects", ("*",), "view"),
    ("GET", r"/api/settings", ("*",), "view"),
    ("GET", r"/api/customers", ("customers", "booking", "recovery", "documents", "portal", "customer_logins", "units"), "view"),
    ("GET", r"/api/agents", ("agents", "booking"), "view"),
    ("GET", r"/api/vendors", ("vendors", "procurement"), "view"),
    ("GET", r"/api/budget/categories", ("budget", "procurement"), "view"),
    ("GET", r"/api/projects/pay-plans", ("payplans", "booking", "projects"), "view"),
    ("GET", r"/api/projects/\d+/installment-template", ("payplans", "booking", "projects"), "view"),
    ("GET", r"/api/possession/templates", ("units",), "view"),
    ("GET", r"/api/document-templates", ("documents",), "view"),
    # --- dashboard / overview
    ("GET", r"/api/dashboard", ("dashboard",), "view"),
    ("GET", r"/api/audit", ("activity",), "view"),
    # --- projects
    ("POST", r"/api/projects", ("projects",), "add"),
    ("GET", r"/api/projects/\d+", ("projects",), "view"),
    ("PUT", r"/api/projects/\d+", ("projects",), "edit"),
    ("DELETE", r"/api/projects/\d+", ("projects",), "delete"),
    ("PUT", r"/api/projects/\d+/installment-template", ("payplans",), "edit"),
    ("DELETE", r"/api/projects/\d+/installment-template", ("payplans",), "delete"),
    ("POST", r"/api/projects/\d+/installment-template/preview", ("payplans", "booking"), "view"),
    # --- units, holds, possession
    ("GET", r"/api/units(/\d+(/holds|/checklist)?)?", ("units", "booking"), "view"),
    ("POST", r"/api/units", ("units",), "add"),
    ("PUT", r"/api/units/\d+", ("units",), "edit"),
    ("DELETE", r"/api/units/\d+", ("units",), "delete"),
    ("PUT", r"/api/units/\d+/status", ("units",), "edit"),
    ("POST", r"/api/units/\d+/holds", ("units",), "add"),
    ("POST", r"/api/units/\d+/possession", ("units",), "edit"),
    ("GET", r"/api/holds/\d+", ("units",), "view"),
    ("POST", r"/api/holds/\d+/release", ("units",), "edit"),
    ("POST", r"/api/holds/expire-due", ("units",), "edit"),
    ("GET", r"/api/possession/(units/\d+/checklist|checklists/\d+)", ("units",), "view"),
    ("POST", r"/api/possession/units/\d+/checklist", ("units",), "add"),
    ("PUT", r"/api/possession/checklists/\d+", ("units",), "edit"),
    ("POST", r"/api/possession/checklists/\d+/complete", ("units",), "edit"),
    ("POST", r"/api/possession/templates", ("units",), "add"),
    ("PUT", r"/api/possession/templates/\d+", ("units",), "edit"),
    # --- bookings
    ("GET", r"/api/bookings(/\d+/cancel-preview)?", ("booking", "customers", "recovery"), "view"),
    ("POST", r"/api/bookings/plan-preview", ("booking",), "view"),
    ("POST", r"/api/bookings", ("booking",), "add"),
    ("POST", r"/api/bookings/\d+/cancel", ("booking",), "delete"),
    ("POST", r"/api/bookings/\d+/transfer", ("booking",), "edit"),
    # --- customers
    ("POST", r"/api/customers", ("customers", "booking"), "add"),
    ("GET", r"/api/customers/\d+", ("customers", "booking", "recovery", "documents"), "view"),
    ("PUT", r"/api/customers/\d+", ("customers",), "edit"),
    ("DELETE", r"/api/customers/\d+", ("customers",), "delete"),
    # --- recovery / payments / demand
    ("GET", r"/api/recovery(/calendar)?", ("recovery",), "view"),
    ("POST", r"/api/payments", ("recovery",), "add"),
    ("GET", r"/api/demand-notices", ("demand", "recovery"), "view"),
    ("GET", r"/api/portal", ("portal", "recovery", "documents"), "view"),
    # --- documents
    ("POST", r"/api/document-templates/preview", ("documents",), "view"),
    ("GET", r"/api/document-templates/\d+", ("documents",), "view"),
    ("POST", r"/api/document-templates", ("documents",), "edit"),
    ("PUT", r"/api/document-templates/\d+", ("documents",), "edit"),
    ("GET", r"/api/customer-documents", ("documents",), "view"),
    ("POST", r"/api/customer-documents", ("documents",), "add"),
    ("PATCH", r"/api/customer-documents/\d+", ("documents",), "edit"),
    ("GET", r"/documents/\d+", ("documents",), "view"),
    # --- procurement & vendors
    ("GET", r"/api/purchase-orders(/\d+)?", ("procurement",), "view"),
    ("POST", r"/api/purchase-orders", ("procurement",), "add"),
    ("PUT", r"/api/purchase-orders/\d+/status", ("procurement",), "edit"),
    ("POST", r"/api/vendor-payments", ("procurement",), "add"),
    ("GET", r"/api/vendors/\d+", ("vendors", "procurement"), "view"),
    ("POST", r"/api/vendors", ("vendors",), "add"),
    ("PUT", r"/api/vendors/\d+", ("vendors",), "edit"),
    ("DELETE", r"/api/vendors/\d+", ("vendors",), "delete"),
    # --- contractors, materials, site
    ("GET", r"/api/contractors(/\d+)?", ("contractors",), "view"),
    ("POST", r"/api/contractors", ("contractors",), "add"),
    ("PUT", r"/api/contractors/\d+", ("contractors",), "edit"),
    ("DELETE", r"/api/contractors/\d+", ("contractors",), "delete"),
    ("POST", r"/api/contractors/\d+/(assign|pay)", ("contractors",), "add"),
    ("GET", r"/api/inventory(/\d+)?", ("inventory",), "view"),
    ("POST", r"/api/inventory", ("inventory",), "add"),
    ("PUT", r"/api/inventory/\d+", ("inventory",), "edit"),
    ("POST", r"/api/inventory/\d+/move", ("inventory",), "add"),
    ("GET", r"/api/site-logs", ("site", "projects"), "view"),
    ("POST", r"/api/site-logs", ("site",), "add"),
    ("PUT", r"/api/site-logs/\d+", ("site",), "edit"),
    ("DELETE", r"/api/site-logs/\d+", ("site",), "delete"),
    # --- finance
    ("GET", r"/api/ledger", ("accounts",), "view"),
    ("POST", r"/api/ledger", ("accounts",), "add"),
    ("DELETE", r"/api/ledger/\d+", ("accounts",), "delete"),
    ("GET", r"/api/budget/(lines|summary)", ("budget", "projects"), "view"),
    ("POST", r"/api/budget/categories", ("budget",), "add"),
    ("DELETE", r"/api/budget/categories/\d+", ("budget",), "delete"),
    ("POST", r"/api/budget/lines", ("budget",), "add"),
    ("POST", r"/api/budget/lines/\d+/revise", ("budget",), "edit"),
    ("GET", r"/api/reports/(ageing|sales)", ("reports",), "view"),
    # --- stakeholders
    ("GET", r"/api/agents/\d+", ("agents",), "view"),
    ("POST", r"/api/agents", ("agents",), "add"),
    ("PUT", r"/api/agents/\d+", ("agents",), "edit"),
    ("DELETE", r"/api/agents/\d+", ("agents",), "delete"),
    ("POST", r"/api/agents/\d+/(pay|bonus)", ("agents",), "add"),
    ("GET", r"/api/investors(/\d+)?", ("investors",), "view"),
    ("POST", r"/api/investors", ("investors",), "add"),
    ("PUT", r"/api/investors/\d+", ("investors",), "edit"),
    ("DELETE", r"/api/investors/\d+", ("investors",), "delete"),
    ("POST", r"/api/investors/\d+/(contribute|distribute)", ("investors",), "add"),
    ("GET", r"/api/partners(/\d+)?", ("partners",), "view"),
    ("POST", r"/api/partners", ("partners",), "add"),
    ("PUT", r"/api/partners/\d+", ("partners",), "edit"),
    ("DELETE", r"/api/partners/\d+", ("partners",), "delete"),
    ("POST", r"/api/partners/\d+/(contribute|distribute)", ("partners",), "add"),
    ("GET", r"/api/entities(/[a-z_]+/\d+)?", ("parties",), "view"),
    # --- customer portal logins
    ("GET", r"/api/portal-access", ("customer_logins",), "view"),
    ("POST", r"/api/portal-access", ("customer_logins",), "add"),
    ("POST", r"/api/portal-access/\d+/(reset-password|status)", ("customer_logins",), "edit"),
]
ROUTE_RULES = [(set(m.split(",")), re.compile(p + r"/?$"), mods, act) for m, p, mods, act in _R]


def match_route(method: str, path: str):
    """Return (modules, action) for a route, or None when the route is admin-only."""
    m = "GET" if method == "HEAD" else method
    for methods, rx, mods, act in ROUTE_RULES:
        if m in methods and rx.match(path):
            return mods, act
    return None


def normalize_permissions(raw: dict) -> dict:
    """Validate {module: {view,add,edit,delete}} coming from the admin UI."""
    out = {}
    for key, flags in (raw or {}).items():
        if key not in MODULE_ACTIONS:
            continue
        allowed = MODULE_ACTIONS[key]
        row = {a: bool((flags or {}).get(a)) and a in allowed for a in ACTIONS}
        if any(row[a] for a in ("add", "edit", "delete")):
            row["view"] = True  # you can't change what you can't see
        if any(row.values()):
            out[key] = row
    return out


def preset_permissions(preset: str) -> dict:
    p = PRESETS.get(preset)
    if not p:
        raise ValueError("Unknown preset")
    letters = {"v": "view", "a": "add", "e": "edit", "d": "delete"}
    return normalize_permissions({k: {letters[c]: True for c in v} for k, v in p["perms"].items()})


def catalogue() -> dict:
    return {
        "actions": ACTIONS,
        "modules": [{"key": k, "label": l, "group": g, "actions": list(a), "project_scoped": s,
                     "needs_all_projects": k in NEEDS_ALL_PROJECTS} for k, l, g, a, s in MODULES],
        "presets": [{"key": k, "label": v["label"], "permissions": preset_permissions(k)} for k, v in PRESETS.items()],
    }
