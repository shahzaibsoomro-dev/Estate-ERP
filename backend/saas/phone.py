"""Pakistani-first phone numbers for company contacts.

Stored canonically so WhatsApp links and letterheads stay consistent:
  mobile    03XX-XXXXXXX
  landline  0XX-XXXXXXX / 0XXX-XXXXXX
  other     +<country><national>  (E.164-ish)
"""
from __future__ import annotations

import re

# 0 + 2-digit area codes used as 03-digit prefixes (021 Karachi, 042 Lahore, …).
_AREA_3 = {
    "021", "022", "040", "041", "042", "043", "044", "046", "047", "048", "049",
    "051", "052", "053", "054", "055", "056", "057", "061", "062", "063", "064",
    "065", "068", "071", "081", "086", "091",
}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _digits(raw: str) -> str:
    return re.sub(r"\D", "", raw or "")


def _format_pk_national(d: str) -> str:
    if d.startswith("03") and len(d) == 11:
        return f"{d[:4]}-{d[4:]}"
    if d[:3] in _AREA_3:
        return f"{d[:3]}-{d[3:]}"
    if len(d) >= 10:
        return f"{d[:4]}-{d[4:]}"
    return d


def normalize_phone(raw: str | None) -> str | None:
    """Return a canonical phone string, or None if blank. Raises ValueError if unusable."""
    text = (raw or "").strip()
    if not text:
        return None
    if re.search(r"[A-Za-z]", text):
        raise ValueError("Phone number cannot contain letters")

    plus = text.startswith("+") or text.startswith("00")
    d = _digits(text)
    if text.startswith("00"):
        d = d[2:] if d.startswith("00") else d
        plus = True

    if not d or len(d) < 10 or len(d) > 15:
        raise ValueError("Enter a Pakistani mobile (03XX-XXXXXXX), a landline, or an international number starting with +")

    # Country code 92 → national 0…
    if d.startswith("92") and len(d) >= 12:
        d = "0" + d[2:]
        plus = False

    # Mobile typed without the leading 0 (3001234567).
    if len(d) == 10 and d.startswith("3"):
        d = "0" + d

    if d.startswith("03"):
        if len(d) != 11:
            raise ValueError("Pakistani mobiles are 11 digits, e.g. 0300-1234567")
        return _format_pk_national(d)

    if d.startswith("0") and 10 <= len(d) <= 11:
        return _format_pk_national(d)

    if plus and 10 <= len(d) <= 15:
        return f"+{d}"

    raise ValueError("Enter a Pakistani mobile (03XX-XXXXXXX), a landline, or an international number starting with +")


def normalize_email(raw: str | None) -> str | None:
    email = (raw or "").strip().lower()
    if not email:
        return None
    if not _EMAIL_RE.match(email):
        raise ValueError("Enter a valid contact email")
    return email
