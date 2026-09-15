"""Sign-in helper for command-line scripts (verify.py, simulate.py).

Set ERP_SCRIPT_EMAIL / ERP_SCRIPT_PASSWORD to a staff account (admin or superadmin).
Installs a global urllib opener that keeps the session cookie and adds the CSRF header.
"""
import http.cookiejar
import json
import os
import sys
import urllib.error
import urllib.request


class _CsrfHandler(urllib.request.BaseHandler):
    def __init__(self):
        self.token = ""

    def http_request(self, req):
        if req.get_method() not in ("GET", "HEAD", "OPTIONS") and self.token:
            req.add_unredirected_header("X-CSRF-Token", self.token)
        return req

    https_request = http_request


def install_script_auth(base: str) -> None:
    email = os.environ.get("ERP_SCRIPT_EMAIL")
    password = os.environ.get("ERP_SCRIPT_PASSWORD")
    if not email or not password:
        sys.exit(
            "This script calls the protected API. Set ERP_SCRIPT_EMAIL and ERP_SCRIPT_PASSWORD\n"
            "to a staff account, e.g.:\n"
            "  python -m backend.manage create-user --role admin --email bot@local --name 'Script Bot'\n"
            "  (sign in once in the browser to set its password)"
        )
    csrf = _CsrfHandler()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()), csrf)
    req = urllib.request.Request(
        base + "/api/auth/login",
        data=json.dumps({"identifier": email, "password": password}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with opener.open(req) as r:
            me = json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"Script sign-in failed ({e.code}): {e.read().decode(errors='replace')}")
    if me.get("must_change_password"):
        sys.exit("The script account still has a temporary password. Sign in once in the browser to set a real one.")
    if me.get("role") not in ("admin", "superadmin"):
        sys.exit("The script account must be an admin or superadmin.")
    csrf.token = me["csrf_token"]
    urllib.request.install_opener(opener)
