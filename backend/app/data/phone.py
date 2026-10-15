"""Phone numbers: normalise to E.164 and hash with a secret key (docs/data-model.md)."""

import hashlib
import hmac
import re

_NON_DIGITS = re.compile(r"\D")


# National number lengths per calling code (VN, SG, PH). A leading 0 is the trunk prefix in VN
# and PH; Singapore numbers have none.
NATIONAL = {"84": (9, 10), "65": (8,), "63": (10,)}
TRUNK_ZERO = {"84", "63"}


def to_e164(raw: str, calling_code: str = "84") -> str | None:
    """A number of the given country, with any spaces, dots or dashes, as E.164, else None.

    Accepts the international form (`+84xxx`, `84xxx`) and the national one (`0xxx` in VN and PH,
    8 digits in SG). Checks the shape only, not whether the prefix exists, because test data uses
    numbers with `000` after the calling code that no carrier issues.
    """
    digits = _NON_DIGITS.sub("", raw)
    lengths = NATIONAL[calling_code]
    if digits.startswith(calling_code) and len(digits) - len(calling_code) in lengths:
        national = digits[len(calling_code) :]
    elif calling_code in TRUNK_ZERO and digits.startswith("0") and len(digits) - 1 in lengths:
        national = digits[1:]
    elif calling_code not in TRUNK_ZERO and len(digits) in lengths:
        national = digits
    else:
        return None
    return f"+{calling_code}{national}"


def phone_hash(e164: str, key: bytes) -> str:
    """HMAC-SHA256. A plain hash of a phone number can be reversed by trying every number."""
    return hmac.new(key, e164.encode(), hashlib.sha256).hexdigest()
