"""Shared capital-provider logic for investors and partners."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from backend.database import fetch_all, fetch_one
from backend.services import audit as audit_svc

RETURN_TYPES = ("Monthly Return", "Profit Sharing")
CATCH_UP_POLICIES = ("none", "lump_sum", "spread")
PROFIT_SHARE_BASES = ("monthly", "milestone", "quarterly", "project", "occasional")
PARTNER_PROFIT_BASES = ("project", "milestone", "quarterly", "occasional")
PAYOUT_OCCASIONS = ("completion", "milestone", "quarterly", "other")


@dataclass(frozen=True)
class CapitalConfig:
    label: str  # Investor / Partner
    entity: str  # investor / partner
    person_table: str
    agreement_table: str
    contribution_table: str
    distribution_table: str
    person_fk: str  # investor_id / partner_id
    type_column: str  # investor_type / partner_type
    require_project: bool = False


INVESTOR = CapitalConfig(
    label="Investor",
    entity="investor",
    person_table="investors",
    agreement_table="investor_agreements",
    contribution_table="investor_contributions",
    distribution_table="investor_distributions",
    person_fk="investor_id",
    type_column="investor_type",
)

PARTNER = CapitalConfig(
    label="Partner",
    entity="partner",
    person_table="partners",
    agreement_table="partner_agreements",
    contribution_table="partner_contributions",
    distribution_table="partner_distributions",
    person_fk="partner_id",
    type_column="partner_type",
    require_project=True,
)


def _clean(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _person_status(raw) -> str:
    status = (_clean(raw) or "active").lower().replace(" ", "_")
    if status == "inactive":
        return "withdrawn"
    if status not in ("active", "completed", "withdrawn"):
        return "active"
    return status


def _normalize_return_type(raw) -> str:
    text = (_clean(raw) or "Profit Sharing").replace("_", " ").strip().lower()
    if text in ("monthly return", "monthly"):
        return "Monthly Return"
    if text in ("profit sharing", "profit share", "profit"):
        return "Profit Sharing"
    return "Profit Sharing"


def _normalize_catch_up(raw) -> str:
    text = (_clean(raw) or "lump_sum").lower().replace(" ", "_").replace("-", "_")
    if text in ("lump", "lumpsum", "one_lump", "one_time"):
        return "lump_sum"
    if text in ("spread", "amortize", "instalments", "installments"):
        return "spread"
    if text in ("none", "waive", "waived", "no_catch_up"):
        return "none"
    if text in CATCH_UP_POLICIES:
        return text
    return "lump_sum"


def _normalize_profit_basis(raw) -> str | None:
    text = (_clean(raw) or "").lower().replace(" ", "_").replace("-", "_")
    if not text:
        return None
    aliases = {
        "month": "monthly",
        "months": "monthly",
        "quarter": "quarterly",
        "quarters": "quarterly",
        "milestones": "milestone",
        "construction": "milestone",
        "whole_project": "project",
        "end": "project",
        "project_end": "project",
        "completion": "project",
        "after_completion": "project",
        "adhoc": "occasional",
        "ad_hoc": "occasional",
        "other": "occasional",
        "occasion": "occasional",
        "occasions": "occasional",
    }
    text = aliases.get(text, text)
    return text if text in PROFIT_SHARE_BASES else None


def _parse_date(raw) -> date | None:
    text = _clean(raw)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _months_between(start: date, end: date) -> int:
    """Whole calendar months from start's month up to (not including) end's month."""
    if end <= start:
        return 0
    return (end.year - start.year) * 12 + (end.month - start.month)


def _add_months(d: date, months: int) -> date:
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    day = min(d.day, [31, 29 if y % 4 == 0 and (y % 100 != 0 or y % 400 == 0) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
    return date(y, m, day)


def _normalize_occasion(raw) -> str | None:
    text = (_clean(raw) or "").lower().replace(" ", "_").replace("-", "_")
    if not text:
        return None
    aliases = {
        "complete": "completion",
        "completed": "completion",
        "project": "completion",
        "project_end": "completion",
        "end": "completion",
        "milestones": "milestone",
        "construction": "milestone",
        "quarter": "quarterly",
        "quarters": "quarterly",
        "ad_hoc": "other",
        "adhoc": "other",
        "occasional": "other",
        "occasion": "other",
    }
    text = aliases.get(text, text)
    return text if text in PAYOUT_OCCASIONS else "other"


def _compute_return_metrics(ag: dict, principal: int, as_of: date | None = None,
                            allow_monthly: bool = True) -> dict:
    as_of = as_of or date.today()
    inv_date = _parse_date(ag.get("investment_date")) or as_of
    start = _parse_date(ag.get("returns_start_date")) or inv_date
    policy = _normalize_catch_up(ag.get("catch_up_policy"))
    try:
        spread_n = int(ag.get("catch_up_months") or 0)
    except (TypeError, ValueError):
        spread_n = 0
    if policy == "spread" and spread_n < 1:
        spread_n = 1

    monthly_pct = ag.get("monthly_return_pct")
    try:
        monthly_pct = float(monthly_pct) if monthly_pct is not None else None
    except (TypeError, ValueError):
        monthly_pct = None

    monthly_amt = int(round(principal * monthly_pct / 100.0)) if monthly_pct is not None and principal else 0
    silent = _months_between(inv_date, start)
    catch_up_total = silent * monthly_amt if policy != "none" and monthly_amt else 0

    accrued = 0
    catch_up_paid_expected = 0
    regular_periods = 0

    rtype = _normalize_return_type(ag.get("investor_type") or ag.get("partner_type") or ag.get("return_type"))
    if not allow_monthly:
        rtype = "Profit Sharing"
    basis = _normalize_profit_basis(ag.get("profit_share_basis")) or ("project" if not allow_monthly else "project")

    if rtype == "Monthly Return" and monthly_amt > 0:
        if as_of >= start:
            if policy == "lump_sum":
                catch_up_paid_expected = catch_up_total
            elif policy == "spread" and catch_up_total:
                months_since = _months_between(start, as_of) + 1
                installments = min(max(months_since, 0), spread_n)
                per = catch_up_total // spread_n
                rem = catch_up_total - per * spread_n
                catch_up_paid_expected = per * installments + (rem if installments >= spread_n else 0)
            regular_periods = _months_between(start, as_of) + 1
            accrued = catch_up_paid_expected + regular_periods * monthly_amt
        else:
            accrued = 0
    elif rtype == "Profit Sharing":
        # Profit amounts depend on declared profit; track cadence only.
        accrued = 0
        if basis == "monthly" and as_of >= start:
            regular_periods = _months_between(start, as_of) + 1
        elif basis == "quarterly" and as_of >= start:
            regular_periods = (_months_between(start, as_of) // 3) + 1
        elif basis in ("milestone", "project", "occasional"):
            regular_periods = 1 if as_of >= start else 0

    return {
        "returns_start_date": start.isoformat(),
        "catch_up_policy": policy,
        "catch_up_months": spread_n if policy == "spread" else (ag.get("catch_up_months") or None),
        "profit_share_basis": basis if rtype == "Profit Sharing" else (ag.get("profit_share_basis") or None),
        "returns_active": as_of >= start,
        "monthly_return_amount": monthly_amt if rtype == "Monthly Return" else None,
        "silent_months": silent,
        "catch_up_total": catch_up_total,
        "catch_up_due_expected": catch_up_paid_expected,
        "regular_periods_due": regular_periods,
        "accrued_return": accrued,
        "next_return_date": start.isoformat() if as_of < start else _add_months(start, max(regular_periods, 0)).isoformat(),
    }


def list_people(conn, cfg: CapitalConfig, project_ids: list[int] | None = None) -> list[dict]:
    if project_ids:
        ph = ",".join("?" * len(project_ids))
        people = fetch_all(
            conn,
            f"""SELECT DISTINCT p.* FROM {cfg.person_table} p
                JOIN {cfg.agreement_table} a ON a.{cfg.person_fk}=p.id
                WHERE a.project_id IN ({ph})
                ORDER BY p.name""",
            tuple(project_ids),
        )
    else:
        people = fetch_all(conn, f"SELECT * FROM {cfg.person_table} ORDER BY name")
    return [_enrich(conn, cfg, p) for p in people]


def get_person(conn, cfg: CapitalConfig, person_id: int) -> dict | None:
    person = fetch_one(conn, f"SELECT * FROM {cfg.person_table} WHERE id=?", (person_id,))
    if not person:
        return None
    person = _enrich(conn, cfg, person)
    person["contributions"] = fetch_all(
        conn,
        f"""SELECT c.* FROM {cfg.contribution_table} c
            JOIN {cfg.agreement_table} a ON a.id=c.agreement_id
            WHERE a.{cfg.person_fk}=? ORDER BY c.contribution_date DESC, c.id DESC""",
        (person_id,),
    )
    person["distributions"] = fetch_all(
        conn,
        f"""SELECT d.* FROM {cfg.distribution_table} d
            JOIN {cfg.agreement_table} a ON a.id=d.agreement_id
            WHERE a.{cfg.person_fk}=? ORDER BY d.distribution_date DESC, d.id DESC""",
        (person_id,),
    )
    return person


def _enrich(conn, cfg: CapitalConfig, person: dict) -> dict:
    agreements = fetch_all(
        conn, f"SELECT * FROM {cfg.agreement_table} WHERE {cfg.person_fk}=?", (person["id"],),
    )
    total_invested = 0
    total_return = 0
    for ag in agreements:
        contrib = fetch_one(
            conn,
            f"SELECT COALESCE(SUM(amount),0) AS v FROM {cfg.contribution_table} WHERE agreement_id=?",
            (ag["id"],),
        )
        dist = fetch_one(
            conn,
            f"SELECT COALESCE(SUM(amount),0) AS v FROM {cfg.distribution_table} WHERE agreement_id=?",
            (ag["id"],),
        )
        ag["total_contributed"] = contrib["v"] if contrib else 0
        ag["total_distributed"] = dist["v"] if dist else 0
        ag["return_type"] = _normalize_return_type(ag.get(cfg.type_column))
        ag[cfg.type_column] = ag["return_type"]
        principal = ag["total_contributed"] or int(ag.get("investment_amount") or 0)
        metrics = _compute_return_metrics(ag, principal, allow_monthly=(cfg.entity != "partner"))
        ag.update(metrics)
        if cfg.entity == "partner":
            ag["return_type"] = "Profit Sharing"
            ag[cfg.type_column] = "Profit Sharing"
            ag["monthly_return_pct"] = None
            ag["monthly_return_amount"] = None
            ag["accrued_return"] = 0
            ag["catch_up_policy"] = "none"
            ag["catch_up_total"] = 0
            ag["catch_up_due_expected"] = 0
        total_invested += ag["total_contributed"]
        total_return += ag["total_distributed"]
    person["agreements"] = agreements
    person["investment_amount"] = total_invested
    person["total_return_received"] = total_return
    person["outstanding_return"] = max(total_invested - total_return, 0)
    person["master_id"] = ("INV" if cfg.entity == "investor" else "PAR") + f"-{person['id']}"
    first = agreements[0] if agreements else {}
    rtype = first.get("return_type") or _normalize_return_type(first.get(cfg.type_column))
    person["return_type"] = rtype
    person[cfg.type_column] = rtype
    # Legacy alias used by investor UI
    person["investor_type"] = rtype
    person["project_id"] = first.get("project_id")
    person["agreed_amount"] = first.get("investment_amount") or 0
    person["investment_date"] = first.get("investment_date")
    person["monthly_return_pct"] = first.get("monthly_return_pct")
    person["profit_share_pct"] = first.get("profit_share_pct")
    person["returns_start_date"] = first.get("returns_start_date")
    person["catch_up_policy"] = first.get("catch_up_policy")
    person["catch_up_months"] = first.get("catch_up_months")
    person["profit_share_basis"] = first.get("profit_share_basis")
    person["returns_active"] = first.get("returns_active")
    person["monthly_return_amount"] = first.get("monthly_return_amount")
    person["silent_months"] = first.get("silent_months")
    person["catch_up_total"] = first.get("catch_up_total")
    person["accrued_return"] = first.get("accrued_return")
    person["return_due"] = max((first.get("accrued_return") or 0) - total_return, 0) if agreements else 0
    if cfg.entity == "partner":
        person["return_type"] = "Profit Sharing"
        person[cfg.type_column] = "Profit Sharing"
        person["investor_type"] = "Profit Sharing"
        person["monthly_return_pct"] = None
        person["monthly_return_amount"] = None
        person["accrued_return"] = 0
        person["return_due"] = 0
        person["catch_up_policy"] = "none"
        person["payout_note"] = (
            "Partners are not on a monthly return. Pay out after project completion, "
            "a construction milestone, or another recorded occasion."
        )
    if first.get("project_id"):
        proj = fetch_one(conn, "SELECT name FROM projects WHERE id=?", (first["project_id"],))
        person["project_name"] = proj["name"] if proj else None
    else:
        person["project_name"] = None
    return person


def _ensure_agreement(conn, cfg: CapitalConfig, person_id: int) -> int:
    ag = fetch_one(
        conn,
        f"SELECT id FROM {cfg.agreement_table} WHERE {cfg.person_fk}=? ORDER BY id LIMIT 1",
        (person_id,),
    )
    if ag:
        return ag["id"]
    cur = conn.execute(
        f"""INSERT INTO {cfg.agreement_table}({cfg.person_fk}, project_id, {cfg.type_column},
           investment_amount, investment_date, status, catch_up_policy, profit_share_basis)
           VALUES(?,?,?,?,?,?,?,?)""",
        (
            person_id, None, "Profit Sharing", 0, date.today().isoformat(), "active",
            "none" if cfg.entity == "partner" else "lump_sum",
            "project",
        ),
    )
    return cur.lastrowid


def _sync_agreement(conn, cfg: CapitalConfig, person_id: int, data: dict) -> None:
    ag_id = _ensure_agreement(conn, cfg, person_id)
    inv_type = _normalize_return_type(data.get("investor_type") or data.get("partner_type") or data.get("return_type"))
    is_partner = cfg.entity == "partner"
    if is_partner:
        inv_type = "Profit Sharing"
    project_id = data.get("project_id")
    if project_id in ("", None):
        project_id = None
    else:
        try:
            project_id = int(project_id)
        except (TypeError, ValueError):
            project_id = None
        if project_id and not fetch_one(conn, "SELECT id FROM projects WHERE id=?", (project_id,)):
            raise ValueError("Project not found")
    if getattr(cfg, "require_project", False) and not project_id:
        raise ValueError(f"{cfg.label} must be linked to a project")
    try:
        agreed = int(data.get("agreed_amount") or 0)
    except (TypeError, ValueError):
        agreed = 0
    inv_date = _clean(data.get("investment_date")) or date.today().isoformat()
    returns_start = _clean(data.get("returns_start_date")) or inv_date
    catch_up = "none" if is_partner else _normalize_catch_up(data.get("catch_up_policy"))
    try:
        catch_up_months = int(data.get("catch_up_months") or 0) if catch_up == "spread" else None
    except (TypeError, ValueError):
        catch_up_months = None
    if catch_up == "spread":
        if not catch_up_months or catch_up_months < 1:
            raise ValueError("Catch-up spread requires N months (>= 1)")
    else:
        catch_up_months = None

    profit_basis = _normalize_profit_basis(data.get("profit_share_basis"))
    if inv_type == "Profit Sharing" and not profit_basis:
        profit_basis = "project"
    if is_partner:
        if profit_basis not in PARTNER_PROFIT_BASES:
            profit_basis = "project"
    if inv_type != "Profit Sharing":
        profit_basis = profit_basis  # allow storing for later switch; UI may clear

    def _pct(key):
        raw = data.get(key)
        if raw in (None, ""):
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    monthly = _pct("monthly_return_pct")
    profit = _pct("profit_share_pct")
    if is_partner:
        monthly = None
    ag_status = _person_status(data.get("status"))
    conn.execute(
        f"""UPDATE {cfg.agreement_table} SET project_id=?, {cfg.type_column}=?, investment_amount=?,
           investment_date=?, monthly_return_pct=?, profit_share_pct=?, status=?,
           returns_start_date=?, catch_up_policy=?, catch_up_months=?, profit_share_basis=?
           WHERE id=?""",
        (
            project_id, inv_type, agreed, inv_date, monthly, profit, ag_status,
            returns_start, catch_up, catch_up_months, profit_basis, ag_id,
        ),
    )


def _check_cnic(conn, cfg: CapitalConfig, cnic: str | None, person_id: int | None = None) -> None:
    if cnic and fetch_one(conn, f"SELECT id FROM {cfg.person_table} WHERE cnic=? AND id != ?",
                          (cnic, person_id or 0)):
        raise ValueError(f"Another {cfg.label.lower()} already has CNIC {cnic}")


def create_person(conn, cfg: CapitalConfig, data: dict) -> dict:
    name = _clean(data.get("name"))
    if not name:
        raise ValueError(f"{cfg.label} name is required")
    _check_cnic(conn, cfg, _clean(data.get("cnic")))
    status = _person_status(data.get("status"))
    cur = conn.execute(
        f"""INSERT INTO {cfg.person_table}(name, cnic, mobile_number, email, description, status)
           VALUES(?,?,?,?,?,?)""",
        (
            name, _clean(data.get("cnic")), _clean(data.get("mobile_number") or data.get("contact")),
            _clean(data.get("email")), _clean(data.get("description")), status,
        ),
    )
    person_id = cur.lastrowid
    _sync_agreement(conn, cfg, person_id, data)
    audit_svc.log(conn, cfg.entity, person_id, "created", {"name": name})
    return get_person(conn, cfg, person_id)


def update_person(conn, cfg: CapitalConfig, person_id: int, data: dict) -> dict | None:
    if not fetch_one(conn, f"SELECT id FROM {cfg.person_table} WHERE id=?", (person_id,)):
        return None
    name = _clean(data.get("name"))
    if not name:
        raise ValueError(f"{cfg.label} name is required")
    _check_cnic(conn, cfg, _clean(data.get("cnic")), person_id)
    status = _person_status(data.get("status"))
    conn.execute(
        f"""UPDATE {cfg.person_table} SET name=?, cnic=?, mobile_number=?, email=?, description=?, status=?
           WHERE id=?""",
        (
            name, _clean(data.get("cnic")), _clean(data.get("mobile_number") or data.get("contact")),
            _clean(data.get("email")), _clean(data.get("description")), status, person_id,
        ),
    )
    _sync_agreement(conn, cfg, person_id, data)
    return get_person(conn, cfg, person_id)


def delete_person(conn, cfg: CapitalConfig, person_id: int) -> None:
    if not fetch_one(conn, f"SELECT id FROM {cfg.person_table} WHERE id=?", (person_id,)):
        raise ValueError(f"{cfg.label} not found")
    money = fetch_one(
        conn,
        f"""SELECT
             (SELECT COUNT(*) FROM {cfg.contribution_table} c
              JOIN {cfg.agreement_table} a ON a.id=c.agreement_id WHERE a.{cfg.person_fk}=?)
           + (SELECT COUNT(*) FROM {cfg.distribution_table} d
              JOIN {cfg.agreement_table} a ON a.id=d.agreement_id WHERE a.{cfg.person_fk}=?) AS n""",
        (person_id, person_id),
    )
    if money and money["n"]:
        raise ValueError(f"Cannot delete a {cfg.entity} with money history")
    conn.execute(f"DELETE FROM {cfg.agreement_table} WHERE {cfg.person_fk}=?", (person_id,))
    conn.execute(f"DELETE FROM {cfg.person_table} WHERE id=?", (person_id,))


def add_contribution(conn, cfg: CapitalConfig, person_id: int, data: dict) -> dict:
    if not fetch_one(conn, f"SELECT id FROM {cfg.person_table} WHERE id=?", (person_id,)):
        raise ValueError(f"{cfg.label} not found")
    amount = int(data.get("amount") or 0)
    if amount <= 0:
        raise ValueError("Amount must be greater than 0")
    agreement_id = data.get("agreement_id") or _ensure_agreement(conn, cfg, person_id)
    pay_date = _clean(data.get("contribution_date")) or date.today().isoformat()
    conn.execute(
        f"""INSERT INTO {cfg.contribution_table}(agreement_id, amount, contribution_date, notes)
           VALUES(?,?,?,?)""",
        (agreement_id, amount, pay_date, _clean(data.get("notes"))),
    )
    audit_svc.log(conn, cfg.entity, person_id, "contribution", {"amount": amount})
    return get_person(conn, cfg, person_id)


def add_distribution(conn, cfg: CapitalConfig, person_id: int, data: dict) -> dict:
    if not fetch_one(conn, f"SELECT id FROM {cfg.person_table} WHERE id=?", (person_id,)):
        raise ValueError(f"{cfg.label} not found")
    amount = int(data.get("amount") or 0)
    if amount <= 0:
        raise ValueError("Amount must be greater than 0")
    agreement_id = data.get("agreement_id") or _ensure_agreement(conn, cfg, person_id)
    ag = fetch_one(conn, f"SELECT * FROM {cfg.agreement_table} WHERE id=?", (agreement_id,))
    if not ag:
        raise ValueError("Agreement not found")
    pay_date = _clean(data.get("distribution_date")) or date.today().isoformat()
    pay = _parse_date(pay_date) or date.today()
    start = _parse_date(ag.get("returns_start_date")) or _parse_date(ag.get("investment_date"))
    if start and pay < start:
        raise ValueError(
            f"Cannot pay returns before {start.isoformat()} "
            f"(returns start date - silent period still active)"
        )
    occasion = _normalize_occasion(data.get("occasion"))
    if cfg.entity == "partner" and not occasion:
        basis = _normalize_profit_basis(ag.get("profit_share_basis")) or "project"
        occasion = {"project": "completion", "milestone": "milestone", "quarterly": "quarterly"}.get(basis, "other")
    conn.execute(
        f"""INSERT INTO {cfg.distribution_table}(agreement_id, amount, distribution_date, notes, occasion)
           VALUES(?,?,?,?,?)""",
        (agreement_id, amount, pay_date, _clean(data.get("notes")), occasion),
    )
    audit_svc.log(conn, cfg.entity, person_id, "distribution", {"amount": amount})
    return get_person(conn, cfg, person_id)
