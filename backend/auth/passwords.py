"""Password hashing with scrypt (stdlib, memory-hard) + password policy."""
import base64
import hashlib
import hmac
import re
import secrets

from backend.auth.settings import PASSWORD_MIN_LENGTH

_N, _R, _P, _DKLEN = 2 ** 14, 8, 1, 32
_ALGO = "scrypt"


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return f"{_ALGO}${_N}${_R}${_P}${_b64(salt)}${_b64(dk)}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algo, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if algo != _ALGO:
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        dk = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected)
        )
        return hmac.compare_digest(dk, expected)
    except (ValueError, TypeError):
        return False


# Precomputed so that unknown-user logins cost the same time as real ones.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))

_COMMON = {
    "password", "password1", "password123", "1234567890", "12345678910", "qwertyuiop",
    "letmein123", "welcome123", "admin12345", "iloveyou12", "pakistan123", "abc1234567",
}


def password_problems(password: str, email: str | None = None) -> list[str]:
    """Return human-readable reasons the password is unacceptable (empty list = OK)."""
    problems = []
    if len(password) < PASSWORD_MIN_LENGTH:
        problems.append(f"at least {PASSWORD_MIN_LENGTH} characters")
    if len(password) > 256:
        problems.append("at most 256 characters")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        problems.append("both letters and numbers")
    if password.lower() in _COMMON:
        problems.append("not a common password")
    if email and email.split("@")[0].lower() in password.lower() and len(email.split("@")[0]) >= 4:
        problems.append("must not contain your username")
    return problems


def generate_temp_password() -> str:
    """Readable one-time password, e.g. 'Kp7m-Xq3r-T9wz'. Always satisfies the policy."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz"
    digits = "23456789"
    groups = []
    for _ in range(3):
        g = [secrets.choice(alphabet) for _ in range(3)] + [secrets.choice(digits)]
        secrets.SystemRandom().shuffle(g)
        groups.append("".join(g))
    return "-".join(groups)
