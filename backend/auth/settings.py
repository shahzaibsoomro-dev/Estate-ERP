"""Auth configuration. Override via environment variables."""
import os


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


SESSION_COOKIE = "erp_session"
# Idle timeout: session ends after this many minutes without activity.
SESSION_IDLE_MINUTES = _int("ERP_SESSION_IDLE_MINUTES", 120)
# Absolute lifetime: session ends this many hours after login regardless of activity.
SESSION_ABSOLUTE_HOURS = _int("ERP_SESSION_ABSOLUTE_HOURS", 12)
# "auto" = Secure flag when the request came over HTTPS; "1" forces it (use in production behind TLS).
COOKIE_SECURE = os.environ.get("ERP_COOKIE_SECURE", "auto").lower()

# Login throttling (sliding window).
LOGIN_WINDOW_MINUTES = _int("ERP_LOGIN_WINDOW_MINUTES", 15)
LOGIN_MAX_FAILS_PER_ACCOUNT = _int("ERP_LOGIN_MAX_FAILS_PER_ACCOUNT", 5)
LOGIN_MAX_FAILS_PER_IP = _int("ERP_LOGIN_MAX_FAILS_PER_IP", 20)

PASSWORD_MIN_LENGTH = _int("ERP_PASSWORD_MIN_LENGTH", 10)

# Comma-separated list of extra origins allowed for CORS. Empty = same-origin only.
CORS_ORIGINS = [o.strip() for o in os.environ.get("ERP_CORS_ORIGINS", "").split(",") if o.strip()]

ROLES = ("superadmin", "admin", "employee", "customer")
# Roles that work inside a company's ERP (superadmins only in support mode).
COMPANY_STAFF_ROLES = ("admin", "employee")
