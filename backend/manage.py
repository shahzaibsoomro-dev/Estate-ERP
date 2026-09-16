"""Command-line account & company management.

  python -m backend.manage create-superadmin
  python -m backend.manage list-companies
  python -m backend.manage create-user --role admin --company haven --email owner@example.com --name "Owner"
  python -m backend.manage reset-password --email someone@example.com
  python -m backend.manage list-users
  python -m backend.manage demo-users      # dev only: one account per role, one-time passwords
"""
import argparse
import getpass
import sys

from backend.auth import service
from backend.auth.passwords import password_problems
from backend.database import fetch_all, fetch_one, get_db, platform_db
from backend.saas.service import bootstrap_platform, resolve_db_path


def _ask_password(email: str) -> str:
    while True:
        pw = getpass.getpass("Password: ")
        problems = password_problems(pw, email)
        if problems:
            print("Password needs " + ", ".join(problems))
            continue
        if getpass.getpass("Repeat password: ") != pw:
            print("Passwords do not match")
            continue
        return pw


def _company(conn, slug: str) -> dict:
    c = fetch_one(conn, "SELECT * FROM companies WHERE slug=?", (slug,))
    if not c:
        sys.exit(f"No company with slug '{slug}'. Run list-companies.")
    return c


def cmd_create_superadmin(args):
    email = args.email or input("Email: ").strip()
    name = args.name or input("Name: ").strip() or "Super Admin"
    pw = _ask_password(email)
    with platform_db() as conn:
        user, _ = service.create_user(conn, email=email, name=name, role="superadmin",
                                      password=pw, must_change_password=False)
    print(f"Created super admin #{user['id']} {user['email']}. Sign in at /login — you'll land in /console.")


def cmd_list_companies(_args):
    with platform_db() as conn:
        for c in fetch_all(conn, "SELECT id, slug, name, status FROM companies ORDER BY id"):
            print(f"#{c['id']:<3} {c['slug']:<20} {c['status']:<10} {c['name']}")


def cmd_create_user(args):
    with platform_db() as conn:
        cid = None
        if args.role != "superadmin":
            if not args.company:
                sys.exit("--company is required for this role")
            cid = _company(conn, args.company)["id"]
        user, temp = service.create_user(conn, email=args.email, name=args.name, role=args.role,
                                         company_id=cid, customer_id=args.customer_id)
    print(f"Created {user['role']} #{user['id']} {user['email']}")
    print(f"One-time password (must be changed at first sign-in): {temp}")


def cmd_reset_password(args):
    with platform_db() as conn:
        row = fetch_one(conn, "SELECT id FROM users WHERE email=?", (args.email.strip().lower(),))
        if not row:
            sys.exit("No user with that email")
        temp = service.reset_password(conn, row["id"])
    print(f"One-time password: {temp}")


def cmd_list_users(_args):
    with platform_db() as conn:
        for u in service.list_users(conn):
            state = "active" if u["is_active"] else "disabled"
            print(f"#{u['id']:<4} {u['role']:<11} {state:<9} {(u['company_name'] or '—'):<22} {u['email']:<34} {u['name']}")


def cmd_demo_users(_args):
    """Development convenience — never run against real data."""
    with platform_db() as conn:
        company = fetch_one(conn, "SELECT * FROM companies ORDER BY id LIMIT 1")
    with get_db(resolve_db_path(company["db_path"])) as tconn:
        cust = fetch_one(
            tconn,
            """SELECT c.id, c.name, c.cnic FROM customers c JOIN bookings b ON b.customer_id=c.id AND b.status='active'
               GROUP BY c.id ORDER BY COUNT(b.id) DESC, c.id LIMIT 1""",
        )
        project = fetch_one(tconn, "SELECT id, name FROM projects ORDER BY id LIMIT 1")
    specs = [
        ("superadmin", "dev@haven.local", "Developer", None),
        ("admin", "admin@haven.local", "Salman Arif", company["id"]),
        ("employee", "sales@haven.local", "Ayesha Khan", company["id"]),
    ]
    if cust:
        specs.append(("customer", "customer@haven.local", cust["name"], company["id"]))
    with platform_db() as conn:
        for role, email, name, cid in specs:
            if fetch_one(conn, "SELECT id FROM users WHERE email=?", (email,)):
                print(f"{email} already exists — use reset-password")
                continue
            user, temp = service.create_user(
                conn, email=email, name=name, role=role, company_id=cid,
                customer_id=cust["id"] if role == "customer" else None,
                customer_cnic=cust["cnic"] if role == "customer" else None,
                job_title="Sales officer" if role == "employee" else None)
            if role == "employee":
                from backend.auth.permissions import preset_permissions
                service.set_employee_access(conn, user["id"], permissions=preset_permissions("sales"),
                                            all_projects=False, project_ids=[project["id"]])
                name += f" (sales, {project['name']} only)"
            print(f"{role:<11} {email:<24} {temp}   {name}")
    print("These are one-time passwords; each account must set a new one on first sign-in.")


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m backend.manage")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("create-superadmin"); s.add_argument("--email"); s.add_argument("--name")
    s.set_defaults(fn=cmd_create_superadmin)
    sub.add_parser("list-companies").set_defaults(fn=cmd_list_companies)
    s = sub.add_parser("create-user")
    s.add_argument("--role", choices=["superadmin", "admin", "employee", "customer"], required=True)
    s.add_argument("--company", help="company slug (see list-companies)")
    s.add_argument("--email", required=True); s.add_argument("--name", required=True)
    s.add_argument("--customer-id", type=int)
    s.set_defaults(fn=cmd_create_user)
    s = sub.add_parser("reset-password"); s.add_argument("--email", required=True)
    s.set_defaults(fn=cmd_reset_password)
    sub.add_parser("list-users").set_defaults(fn=cmd_list_users)
    sub.add_parser("demo-users").set_defaults(fn=cmd_demo_users)
    args = p.parse_args(argv)
    bootstrap_platform()
    try:
        args.fn(args)
    except ValueError as e:
        sys.exit(f"Error: {e}")


if __name__ == "__main__":
    main()
