"""Users, sessions, login throttling and employee permissions (platform database)."""
import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from backend.auth import permissions as perms
from backend.auth import settings as cfg
from backend.auth.passwords import (
    DUMMY_HASH, generate_temp_password, hash_password, password_problems, verify_password,
)
from backend.database import fetch_all, fetch_one
from backend.saas.service import audit

USER_COLS = """u.id, u.email, u.name, u.role, u.company_id, u.customer_id, u.job_title, u.is_active,
               u.must_change_password, u.all_projects, u.last_login_at, u.created_at, u.updated_at"""
PUBLIC_FIELDS = ("id", "email", "name", "role", "company_id", "customer_id", "job_title", "is_active",
                 "must_change_password", "all_projects", "last_login_at", "created_at")


class AuthError(Exception):
    """Login failed — message is safe to show to the user."""


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def normalize_identifier(identifier: str) -> str:
    return (identifier or "").strip().lower()[:254]


def cnic_digits(cnic: str | None) -> str | None:
    d = "".join(ch for ch in (cnic or "") if ch.isdigit())
    return d if len(d) == 13 else None


# ---------------------------------------------------------------- users
def public_user(u: dict | None) -> dict | None:
    return {k: u[k] for k in PUBLIC_FIELDS if k in u} if u else None


def get_user(conn, user_id: int) -> dict | None:
    return fetch_one(conn, f"SELECT {USER_COLS} FROM users u WHERE u.id=?", (user_id,))


def get_permissions(conn, user_id: int) -> dict:
    rows = fetch_all(conn, "SELECT * FROM employee_permissions WHERE user_id=?", (user_id,))
    return {r["module"]: {a: bool(r[f"can_{a}"]) for a in perms.ACTIONS} for r in rows}


def get_project_ids(conn, user_id: int) -> list[int]:
    return [r["project_id"] for r in fetch_all(
        conn, "SELECT project_id FROM employee_projects WHERE user_id=? ORDER BY project_id", (user_id,))]


def list_users(conn, company_id: int | None = None, roles: tuple = ()) -> list[dict]:
    where, params = [], []
    if company_id is not None:
        where.append("u.company_id=?")
        params.append(company_id)
    if roles:
        where.append(f"u.role IN ({','.join('?' * len(roles))})")
        params.extend(roles)
    sql = f"SELECT {USER_COLS}, c.name AS company_name FROM users u LEFT JOIN companies c ON c.id=u.company_id"
    if where:
        sql += " WHERE " + " AND ".join(where)
    return fetch_all(conn, sql + " ORDER BY u.role, u.name", tuple(params))


def _validate_email(email: str) -> str:
    email = normalize_identifier(email)
    if "@" not in email or "." not in email.split("@")[-1] or " " in email:
        raise ValueError("Enter a valid email address")
    return email


def create_user(conn, *, email: str, name: str, role: str, company_id: int | None = None,
                password: str | None = None, customer_id: int | None = None, customer_cnic: str | None = None,
                job_title: str | None = None, created_by: int | None = None,
                must_change_password: bool = True) -> tuple[dict, str | None]:
    """Create a user. If no password is given a one-time password is generated and returned once."""
    if role not in cfg.ROLES:
        raise ValueError("Invalid role")
    email = _validate_email(email)
    name = (name or "").strip()
    if not name:
        raise ValueError("Name is required")
    if role == "superadmin":
        company_id = None
    elif not company_id:
        raise ValueError("A company is required for this account")
    if role == "customer":
        if not customer_id:
            raise ValueError("Customer accounts must be linked to a customer")
    else:
        customer_id = None
    temp = None
    if password is None:
        temp = password = generate_temp_password()
    else:
        problems = password_problems(password, email)
        if problems:
            raise ValueError("Password needs " + ", ".join(problems))
    try:
        cur = conn.execute(
            """INSERT INTO users(email, name, role, company_id, customer_id, cnic_digits, job_title, password_hash,
                                 created_by, must_change_password, password_changed_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,datetime('now'))""",
            (email, name, role, company_id, customer_id, cnic_digits(customer_cnic) if role == "customer" else None,
             (job_title or "").strip() or None, hash_password(password), created_by, int(must_change_password)),
        )
    except sqlite3.IntegrityError as e:
        if "customer_id" in str(e):
            raise ValueError("This customer already has a portal login") from e
        raise ValueError("A user with this email already exists") from e
    audit(conn, "user.create", company_id=company_id, target_type="user", target_id=cur.lastrowid,
          details={"email": email, "role": role})
    return get_user(conn, cur.lastrowid), temp


def set_employee_access(conn, user_id: int, *, permissions: dict, all_projects: bool, project_ids: list[int]) -> None:
    clean = perms.normalize_permissions(permissions)
    if not all_projects:
        for key in list(clean):
            if key in perms.NEEDS_ALL_PROJECTS:
                clean.pop(key)  # company-wide pages need access to all projects
    conn.execute("DELETE FROM employee_permissions WHERE user_id=?", (user_id,))
    for mod, row in clean.items():
        conn.execute(
            """INSERT INTO employee_permissions(user_id, module, can_view, can_add, can_edit, can_delete)
               VALUES(?,?,?,?,?,?)""",
            (user_id, mod, *(int(row[a]) for a in perms.ACTIONS)),
        )
    conn.execute("DELETE FROM employee_projects WHERE user_id=?", (user_id,))
    if not all_projects:
        for pid in sorted({int(p) for p in project_ids}):
            conn.execute("INSERT INTO employee_projects(user_id, project_id) VALUES(?,?)", (user_id, pid))
    conn.execute("UPDATE users SET all_projects=?, updated_at=datetime('now') WHERE id=?", (int(all_projects), user_id))


def update_user(conn, user_id: int, *, name: str | None = None, role: str | None = None,
                job_title: str | None = None, is_active: bool | None = None, actor_id: int | None = None) -> dict:
    u = get_user(conn, user_id)
    if not u:
        raise LookupError("User not found")
    if actor_id == user_id and (is_active is False or (role and role != u["role"])):
        raise ValueError("You cannot deactivate or change the role of your own account")
    if role and role != u["role"]:
        allowed = {"admin", "employee"}
        if role not in allowed or u["role"] not in allowed:
            raise ValueError("Only admin ↔ employee role changes are allowed")
    if u["role"] == "superadmin" and is_active is False:
        n = fetch_one(conn, "SELECT COUNT(*) n FROM users WHERE role='superadmin' AND is_active=1")["n"]
        if n <= 1:
            raise ValueError("At least one active superadmin must remain")
    conn.execute(
        """UPDATE users SET name=COALESCE(?, name), role=COALESCE(?, role), job_title=COALESCE(?, job_title),
                  is_active=COALESCE(?, is_active), updated_at=datetime('now') WHERE id=?""",
        ((name or "").strip() or None, role, job_title, None if is_active is None else int(is_active), user_id),
    )
    if role == "admin":
        conn.execute("DELETE FROM employee_permissions WHERE user_id=?", (user_id,))
        conn.execute("DELETE FROM employee_projects WHERE user_id=?", (user_id,))
        conn.execute("UPDATE users SET all_projects=1 WHERE id=?", (user_id,))
    if is_active is False or (role and role != u["role"]):
        revoke_user_sessions(conn, user_id)
    audit(conn, "user.update", company_id=u["company_id"], target_type="user", target_id=user_id,
          details={"name": name, "role": role, "is_active": is_active, "job_title": job_title})
    return get_user(conn, user_id)


def reset_password(conn, user_id: int) -> str:
    u = get_user(conn, user_id)
    if not u:
        raise LookupError("User not found")
    temp = generate_temp_password()
    conn.execute(
        """UPDATE users SET password_hash=?, must_change_password=1,
                  password_changed_at=datetime('now'), updated_at=datetime('now') WHERE id=?""",
        (hash_password(temp), user_id),
    )
    revoke_user_sessions(conn, user_id)
    clear_lockout(conn, user_id)
    audit(conn, "user.password_reset", company_id=u["company_id"], target_type="user", target_id=user_id)
    return temp


def clear_lockout(conn, user_id: int) -> None:
    """Forget recent failed sign-ins so a locked-out user can try again immediately."""
    u = fetch_one(conn, "SELECT email, cnic_digits FROM users WHERE id=?", (user_id,))
    if not u:
        return
    idents = [u["email"].lower()] + ([u["cnic_digits"]] if u["cnic_digits"] else [])
    conn.execute(
        f"DELETE FROM login_attempts WHERE success=0 AND identifier IN ({','.join('?' * len(idents))})",
        tuple(idents),
    )


def is_locked(conn, user_id: int) -> bool:
    u = fetch_one(conn, "SELECT email FROM users WHERE id=?", (user_id,))
    return bool(u) and _recent_failures(conn, "identifier", u["email"].lower()) >= cfg.LOGIN_MAX_FAILS_PER_ACCOUNT


def change_password(conn, user_id: int, current: str, new: str, keep_token_hash: str | None) -> None:
    row = fetch_one(conn, "SELECT email, company_id, password_hash FROM users WHERE id=?", (user_id,))
    if not row or not verify_password(current, row["password_hash"]):
        raise ValueError("Current password is incorrect")
    if current == new:
        raise ValueError("New password must be different from the current one")
    problems = password_problems(new, row["email"])
    if problems:
        raise ValueError("Password needs " + ", ".join(problems))
    conn.execute(
        """UPDATE users SET password_hash=?, must_change_password=0,
                  password_changed_at=datetime('now'), updated_at=datetime('now') WHERE id=?""",
        (hash_password(new), user_id),
    )
    conn.execute(
        "UPDATE auth_sessions SET revoked_at=datetime('now') WHERE user_id=? AND token_hash!=? AND revoked_at IS NULL",
        (user_id, keep_token_hash or ""),
    )
    audit(conn, "auth.password_change", company_id=row["company_id"], target_type="user", target_id=user_id,
          user_id=user_id)


# ---------------------------------------------------------------- login
def _recent_failures(conn, column: str, value: str) -> int:
    since = _ts(_now() - timedelta(minutes=cfg.LOGIN_WINDOW_MINUTES))
    row = fetch_one(
        conn,
        f"""SELECT COUNT(*) AS n FROM login_attempts
            WHERE {column}=? AND success=0 AND attempted_at >= ?
              AND attempted_at > COALESCE((SELECT MAX(attempted_at) FROM login_attempts
                                           WHERE {column}=? AND success=1), '')""",
        (value, since, value),
    )
    return row["n"] if row else 0


def _record_attempt(conn, identifier: str, ip: str | None, success: bool) -> None:
    conn.execute(
        "INSERT INTO login_attempts(identifier, ip, success, attempted_at) VALUES(?,?,?,?)",
        (identifier, ip, int(success), _ts(_now())),
    )


def _find_login_user(conn, identifier: str) -> dict | None:
    u = fetch_one(conn, "SELECT * FROM users WHERE email=?", (identifier,))
    if u:
        return u
    digits = cnic_digits(identifier)
    if digits:
        rows = fetch_all(conn, "SELECT * FROM users WHERE role='customer' AND cnic_digits=?", (digits,))
        if len(rows) > 1:
            raise AuthError("This CNIC has accounts with more than one company. Please sign in with your email.")
        return rows[0] if rows else None
    return None


def authenticate(conn, identifier: str, password: str, ip: str | None) -> dict:
    from backend.saas.service import company_state

    ident = normalize_identifier(identifier)
    if not ident or not password:
        raise AuthError("Enter your email and password")
    if (_recent_failures(conn, "identifier", ident) >= cfg.LOGIN_MAX_FAILS_PER_ACCOUNT
            or (ip and _recent_failures(conn, "ip", ip) >= cfg.LOGIN_MAX_FAILS_PER_IP)):
        _record_attempt(conn, ident, ip, False)
        raise AuthError(f"Too many failed attempts. Try again in {cfg.LOGIN_WINDOW_MINUTES} minutes.")
    user = _find_login_user(conn, ident)
    ok = verify_password(password, user["password_hash"] if user else DUMMY_HASH)
    if not user or not ok or not user["is_active"]:
        _record_attempt(conn, ident, ip, False)
        audit(conn, "auth.login_failed", company_id=user["company_id"] if user else None,
              target_type="user", target_id=user["id"] if user else None,
              details={"identifier": ident}, user_id=user["id"] if user else None)
        raise AuthError("Incorrect email or password")
    if user["role"] in ("admin", "employee"):
        state = company_state(conn, user["company_id"])
        if state["staff_blocked"]:
            _record_attempt(conn, ident, ip, True)
            raise AuthError("Your company's account is suspended. Please contact your platform administrator.")
    _record_attempt(conn, ident, ip, True)
    conn.execute("UPDATE users SET last_login_at=datetime('now') WHERE id=?", (user["id"],))
    audit(conn, "auth.login", company_id=user["company_id"], target_type="user", target_id=user["id"],
          user_id=user["id"])
    return user


# ---------------------------------------------------------------- sessions
def create_session(conn, user: dict, ip: str | None, user_agent: str | None,
                   company_id: int | None = None, support_mode: bool = False) -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    hours = 2 if support_mode else cfg.SESSION_ABSOLUTE_HOURS
    expires = _now() + timedelta(hours=hours)
    conn.execute(
        """INSERT INTO auth_sessions(token_hash, user_id, company_id, support_mode, csrf_token, created_at,
                                     last_seen_at, expires_at, ip, user_agent)
           VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (_token_hash(token), user["id"], company_id if company_id is not None else user.get("company_id"),
         int(support_mode), csrf, _ts(_now()), _ts(_now()), _ts(expires), ip, (user_agent or "")[:300]),
    )
    conn.execute("DELETE FROM auth_sessions WHERE expires_at < ? OR (revoked_at IS NOT NULL AND revoked_at < ?)",
                 (_ts(_now()), _ts(_now() - timedelta(days=7))))
    conn.execute("DELETE FROM login_attempts WHERE attempted_at < ?", (_ts(_now() - timedelta(days=30)),))
    return token, csrf


def resolve_session(conn, token: str | None) -> dict | None:
    """Return the signed-in context for a valid session token, else None."""
    if not token or len(token) > 200:
        return None
    th = _token_hash(token)
    row = fetch_one(
        conn,
        f"""SELECT s.csrf_token, s.last_seen_at, s.expires_at, s.revoked_at, s.company_id AS session_company,
                   s.support_mode, {USER_COLS},
                   c.name AS company_name, c.slug AS company_slug, c.db_path AS company_db, c.status AS company_status
            FROM auth_sessions s
            JOIN users u ON u.id=s.user_id
            LEFT JOIN companies c ON c.id=s.company_id
            WHERE s.token_hash=?""",
        (th,),
    )
    if not row or row["revoked_at"] or not row["is_active"]:
        return None
    now = _now()
    if row["expires_at"] < _ts(now):
        return None
    if row["last_seen_at"] < _ts(now - timedelta(minutes=cfg.SESSION_IDLE_MINUTES)):
        conn.execute("UPDATE auth_sessions SET revoked_at=? WHERE token_hash=?", (_ts(now), th))
        return None
    if row["last_seen_at"] < _ts(now - timedelta(minutes=1)):
        conn.execute("UPDATE auth_sessions SET last_seen_at=? WHERE token_hash=?", (_ts(now), th))
    user = {k: row[k] for k in PUBLIC_FIELDS + ("updated_at",)}
    ctx = {
        "user": user,
        "csrf_token": row["csrf_token"],
        "token_hash": th,
        "support_mode": bool(row["support_mode"]),
        "company": None,
        "permissions": None,
        "project_ids": None,   # None = all projects
    }
    if row["session_company"]:
        ctx["company"] = {"id": row["session_company"], "name": row["company_name"], "slug": row["company_slug"],
                          "db_path": row["company_db"], "status": row["company_status"]}
    if user["role"] == "employee":
        ctx["permissions"] = get_permissions(conn, user["id"])
        if not user["all_projects"]:
            ctx["project_ids"] = get_project_ids(conn, user["id"])
    return ctx


def set_session_company(conn, token: str, company_id: int | None, support_mode: bool) -> None:
    conn.execute("UPDATE auth_sessions SET company_id=?, support_mode=? WHERE token_hash=?",
                 (company_id, int(support_mode), _token_hash(token)))


def revoke_session(conn, token: str | None) -> None:
    if token:
        conn.execute("UPDATE auth_sessions SET revoked_at=datetime('now') WHERE token_hash=?",
                     (_token_hash(token),))


def revoke_user_sessions(conn, user_id: int) -> None:
    conn.execute("UPDATE auth_sessions SET revoked_at=datetime('now') WHERE user_id=? AND revoked_at IS NULL",
                 (user_id,))


def count_superadmins(conn) -> int:
    return fetch_one(conn, "SELECT COUNT(*) n FROM users WHERE role='superadmin' AND is_active=1")["n"]
