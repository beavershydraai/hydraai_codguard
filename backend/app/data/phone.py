"""Phone numbers: normalise to E.164, hash with a secret key, and encrypt for storage
(docs/data-model.md).

Every phone number stored in Firestore is encrypted with AES-GCM under PHONE_ENC_KEY (Secret
Manager, 32 bytes, base64). The app decrypts it where a person reads it or a call dials it. The
keyed hash (PHONE_HASH_KEY) stays next to it to match a phone across orders and shops.
"""

import base64
import hashlib
import hmac
import os
import re
from functools import cache

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

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


_PREFIX = "enc:v1:"


@cache
def _cipher(key: str) -> AESGCM:
    return AESGCM(base64.b64decode(key))


def encrypt_phone(phone: str | None) -> str | None:
    """The phone as stored: `enc:v1:` + base64(nonce + ciphertext). None stays None."""
    if not phone or phone.startswith(_PREFIX):
        return phone
    nonce = os.urandom(12)
    sealed = _cipher(os.environ["PHONE_ENC_KEY"]).encrypt(nonce, phone.encode(), None)
    return _PREFIX + base64.b64encode(nonce + sealed).decode()


def decrypt_phone(stored: str | None) -> str | None:
    """The phone as entered. A value stored before encryption (no prefix) is returned as it is."""
    if not stored or not stored.startswith(_PREFIX):
        return stored
    raw = base64.b64decode(stored.removeprefix(_PREFIX))
    return _cipher(os.environ["PHONE_ENC_KEY"]).decrypt(raw[:12], raw[12:], None).decode()
