"""Phone numbers: normalise to E.164 and hash with a secret key (docs/data-model.md)."""

import hashlib
import hmac
import re

_NON_DIGITS = re.compile(r"\D")


def to_e164(raw: str) -> str | None:
    """`0xxx`, `84xxx` or `+84xxx`, with any spaces, dots or dashes -> `+84xxx`, else None.

    Checks the shape only (9 or 10 national digits), not whether the prefix exists, because test
    data uses `+84000...` numbers that no carrier issues.
    """
    digits = _NON_DIGITS.sub("", raw)
    if digits.startswith("84") and len(digits) in (11, 12):
        national = digits[2:]
    elif digits.startswith("0") and len(digits) in (10, 11):
        national = digits[1:]
    else:
        return None
    return f"+84{national}"


def phone_hash(e164: str, key: bytes) -> str:
    """HMAC-SHA256. A plain hash of a phone number can be reversed by trying every number."""
    return hmac.new(key, e164.encode(), hashlib.sha256).hexdigest()
